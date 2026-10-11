"""Phase 1 security: RSA-encrypted passwords, password rules, login lock, error codes, HashTable."""

import pytest
from conftest import DEFAULT_PASSWORD, register

from config import settings
from data_structures import HashTable
from password_crypto import encrypt_for_tests
from password_policy import failed_rules
from services.login_attempts import LoginAttemptTracker


@pytest.fixture
def require_encryption():
    """Turn on production behaviour (plain-text passwords rejected) for one test."""
    object.__setattr__(settings, "require_encrypted_passwords", True)
    yield
    object.__setattr__(settings, "require_encrypted_passwords", False)


def new_user(email="nuevo@club.com", password=DEFAULT_PASSWORD, first="Laura", last="Gomez", role="COACH"):
    return {"first_name": first, "last_name": last, "email": email, "password": password, "role": role}


# ------------------------------------------------------------------ RSA encryption
def test_public_key_is_published(client):
    body = client.get("/api/auth/public-key").json()
    assert body["algorithm"] == "RSA-OAEP-256"
    assert len(body["key"]) > 300
    assert body["password_rules"] == {"min_length": 8, "max_length": 64}


def test_register_and_login_with_encrypted_password(client, require_encryption):
    created = client.post("/api/auth/register", json=new_user(password=encrypt_for_tests(DEFAULT_PASSWORD)))
    assert created.status_code == 201, created.text
    assert "password" not in created.text.lower().replace("password_rules", "")
    login = client.post("/api/auth/login", json={"email": "nuevo@club.com", "password": encrypt_for_tests(DEFAULT_PASSWORD)})
    assert login.status_code == 200


def test_plain_text_password_rejected_when_encryption_required(client, require_encryption):
    response = client.post("/api/auth/register", json=new_user())
    assert response.status_code == 400
    assert response.json()["code"] == "PASSWORD_NOT_ENCRYPTED"


def test_tampered_ciphertext_is_rejected(client):
    tampered = encrypt_for_tests(DEFAULT_PASSWORD)[:-8] + "AAAAAAA="
    response = client.post("/api/auth/register", json=new_user(password=tampered))
    assert response.status_code == 400
    assert response.json()["code"] == "PASSWORD_DECRYPTION_FAILED"


def test_stored_password_is_a_bcrypt_hash(client):
    import database
    from models import User
    client.post("/api/auth/register", json=new_user())
    with database.SessionLocal() as db:
        stored = db.query(User).filter(User.email == "nuevo@club.com").one().password_hash
    assert stored.startswith("$2b$12$") and DEFAULT_PASSWORD not in stored


# ------------------------------------------------------------------ password rules
@pytest.mark.parametrize(("password", "rule"), [
    ("Ab#1", "length"),
    ("A" * 60 + "b#12345", "length"),
    ("tactica#2026", "upper"),
    ("TACTICA#2026", "lower"),
    ("Tactica#Club", "digit"),
    ("Tactica2026", "special"),
    ("Tactica #2026", "no_spaces"),
    ("Laura#2026x", "no_personal_data"),
    ("Password123", "special"),
])
def test_password_rules(password, rule):
    assert rule in failed_rules(password, email="nuevo@club.com", first_name="Laura", last_name="Gomez")


def test_valid_password_passes_every_rule():
    assert failed_rules("Tactica#2026", email="nuevo@club.com", first_name="Laura", last_name="Gomez") == []


def test_common_password_is_rejected():
    assert "not_common" in failed_rules("Password1")


def test_register_rejects_weak_password_with_rule_list(client):
    response = client.post("/api/auth/register", json=new_user(password="laura123"))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "PASSWORD_POLICY"
    assert {"upper", "special", "no_personal_data"} <= set(body["failed_rules"])


def test_change_password_rules_and_reuse(client, coach):
    headers = coach["headers"]
    weak = client.post("/api/auth/change-password", headers=headers,
                       json={"current_password": DEFAULT_PASSWORD, "new_password": "corta"})
    assert weak.json()["code"] == "PASSWORD_POLICY"
    reused = client.post("/api/auth/change-password", headers=headers,
                         json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD})
    assert reused.json()["code"] == "PASSWORD_REUSED"
    wrong = client.post("/api/auth/change-password", headers=headers,
                        json={"current_password": "Otra#Clave1", "new_password": "Nueva#Clave456"})
    assert wrong.json()["code"] == "CURRENT_PASSWORD_INCORRECT"
    ok = client.post("/api/auth/change-password", headers=headers,
                     json={"current_password": DEFAULT_PASSWORD, "new_password": "Nueva#Clave456"})
    assert ok.status_code == 204


# ------------------------------------------------------------------ error codes
def test_error_codes(client, coach):
    duplicated = client.post("/api/auth/register", json=new_user(email="coach@test.com"))
    assert (duplicated.status_code, duplicated.json()["code"]) == (409, "EMAIL_TAKEN")
    wrong = client.post("/api/auth/login", json={"email": "coach@test.com", "password": "Otra#Clave1"})
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["remaining_attempts"] == 4


# ------------------------------------------------------------------ login lock
def test_account_locks_after_five_failed_attempts(client, coach):
    for attempt in range(4):
        response = client.post("/api/auth/login", json={"email": "coach@test.com", "password": "Otra#Clave1"})
        assert response.status_code == 401
    fifth = client.post("/api/auth/login", json={"email": "coach@test.com", "password": "Otra#Clave1"})
    assert fifth.status_code == 429
    assert fifth.json()["code"] == "ACCOUNT_LOCKED"
    assert int(fifth.headers["Retry-After"]) > 0
    # Even the right password is refused while locked.
    blocked = client.post("/api/auth/login", json={"email": "coach@test.com", "password": DEFAULT_PASSWORD})
    assert blocked.status_code == 429


def test_lock_expires_and_success_clears_counter():
    now = [1000.0]
    tracker = LoginAttemptTracker.__new__(LoginAttemptTracker)
    LoginAttemptTracker.__init__(tracker, max_failed=3, lock_minutes=1, clock=lambda: now[0])
    assert tracker.record_failure("a@b.com") == 2
    tracker.record_success("a@b.com")
    assert tracker.record_failure("a@b.com") == 2
    tracker.record_failure("a@b.com")
    assert tracker.record_failure("a@b.com") == 0
    assert tracker.seconds_locked("a@b.com") == 60
    now[0] += 61
    assert tracker.seconds_locked("a@b.com") == 0


def test_security_headers(client):
    response = client.get("/api/auth/public-key")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------------ HashTable
def test_hash_table_put_get_update_remove():
    table: HashTable[str, int] = HashTable(capacity=4)
    table.put("a", 1)
    table.put("b", 2)
    table.put("a", 10)
    assert table.get("a") == 10 and table.get("b") == 2 and len(table) == 2
    assert "a" in table and "z" not in table
    assert table.remove("a") is True and table.remove("a") is False
    assert table.get("a") is None and len(table) == 1


def test_hash_table_resizes_and_keeps_every_key():
    table: HashTable[int, str] = HashTable(capacity=2)
    for number in range(100):
        table.put(number, str(number))
    assert len(table) == 100
    assert table.capacity >= 128
    assert table.load_factor <= HashTable.MAX_LOAD_FACTOR
    assert all(table.get(number) == str(number) for number in range(100))


def test_hash_table_handles_collisions():
    class SameHash:
        def __init__(self, name):
            self.name = name

        def __hash__(self):
            return 7

        def __eq__(self, other):
            return isinstance(other, SameHash) and other.name == self.name

    table: HashTable[SameHash, int] = HashTable(capacity=8)
    first, second = SameHash("x"), SameHash("y")
    table.put(first, 1)
    table.put(second, 2)
    assert table.get(first) == 1 and table.get(second) == 2


def test_register_helper_still_works(client):
    account = register(client, "otro@club.com", "ANALYST")
    assert account["user"]["role"] == "ANALYST"
