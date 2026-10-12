"""Profile editing, password change sessions and password recovery by e-mail."""

import pytest

import routers.auth as auth_router
from conftest import DEFAULT_PASSWORD
from services.mailer import MailMessage, Mailer, password_recovery_message


class FakeMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    def send(self, message: MailMessage) -> None:
        self.sent.append(message)


@pytest.fixture
def mailer(monkeypatch):
    fake = FakeMailer()
    monkeypatch.setattr(auth_router, "get_mailer", lambda: fake)
    return fake


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_ends_old_sessions(client, coach):
    other_device = client.post("/api/auth/login", json={"email": "coach@test.com", "password": DEFAULT_PASSWORD}).json()
    changed = client.post("/api/auth/change-password", headers=coach["headers"],
                          json={"current_password": DEFAULT_PASSWORD, "new_password": "Nueva#Clave456"})
    assert changed.status_code == 200

    for old in (coach["headers"], bearer(other_device["access_token"])):
        rejected = client.get("/api/auth/me", headers=old)
        assert (rejected.status_code, rejected.json()["code"]) == (401, "SESSION_EXPIRED")
    assert client.get("/api/auth/me", headers=bearer(changed.json()["access_token"])).status_code == 200
    assert client.post("/api/auth/login", json={"email": "coach@test.com", "password": "Nueva#Clave456"}).status_code == 200


def test_recovery_sends_a_one_time_link_by_email(client, coach, mailer):
    response = client.post("/api/auth/password-recovery", json={"email": "COACH@test.com"})
    assert response.status_code == 202
    assert len(mailer.sent) == 1
    message = mailer.sent[0]
    assert message.to == "coach@test.com"
    assert "/restablecer#token=" in message.text and "/restablecer#token=" in message.html
    token = message.text.split("#token=")[1].split()[0]

    assert client.post("/api/auth/password-reset", json={"token": token, "new_password": "Nueva#Clave456"}).status_code == 204
    # The link works only once, and the sessions opened with the old password are closed.
    assert client.post("/api/auth/password-reset", json={"token": token, "new_password": "Otra#Clave789"}).status_code == 400
    assert client.get("/api/auth/me", headers=coach["headers"]).status_code == 401


def test_recovery_does_not_reveal_unknown_emails(client, coach, mailer):
    known = client.post("/api/auth/password-recovery", json={"email": "coach@test.com"}).json()
    unknown = client.post("/api/auth/password-recovery", json={"email": "nadie@test.com"})
    assert unknown.status_code == 202
    assert unknown.json()["message"] == known["message"]
    assert "reset_token" not in unknown.json()
    assert len(mailer.sent) == 1  # only the registered account got an e-mail


def test_recovery_email_escapes_html():
    message = password_recovery_message(email="a@test.com", first_name="<script>x</script>", token="abc")
    assert "<script>" not in message.html and "&lt;script&gt;" in message.html


def test_profile_update_validates_fields(client, coach):
    headers = coach["headers"]
    saved = client.put("/api/auth/me", headers=headers,
                       json={"first_name": "  Mateo   Andrés ", "last_name": "Ríos", "phone": "+57 300 123 4567"})
    assert saved.status_code == 200
    assert (saved.json()["first_name"], saved.json()["phone"]) == ("Mateo Andrés", "+57 300 123 4567")

    for bad in ({"first_name": "   "}, {"phone": "llámame"}, {"profile_image_url": "http://example.com/a.png"}):
        assert client.put("/api/auth/me", headers=headers, json=bad).status_code == 422

    cleared = client.put("/api/auth/me", headers=headers, json={"phone": ""})
    assert cleared.json()["phone"] is None
    # Role, e-mail and team can never be changed from the profile.
    ignored = client.put("/api/auth/me", headers=headers, json={"role": "ADMINISTRATOR", "email": "x@test.com"})
    assert (ignored.json()["role"], ignored.json()["email"]) == ("COACH", "coach@test.com")


def test_mail_provider_is_chosen_by_configuration(monkeypatch):
    import dataclasses

    import services.mailer as mailer_module
    base = mailer_module.settings
    cases = [({"mail_provider": "", "mail_from": "x@test.com"}, type(None)),
             ({"mail_provider": "smtp", "mail_from": ""}, type(None)),
             ({"mail_provider": "smtp", "mail_from": "x@test.com"}, mailer_module.SmtpMailer),
             ({"mail_provider": "brevo", "mail_from": "x@test.com"}, mailer_module.BrevoMailer)]
    for overrides, expected in cases:
        monkeypatch.setattr(mailer_module, "settings", dataclasses.replace(base, **overrides))
        assert type(mailer_module.get_mailer()) is expected


def test_brevo_mailer_reports_rejections(monkeypatch):
    import dataclasses

    import httpx

    import services.mailer as mailer_module
    monkeypatch.setattr(mailer_module, "settings", dataclasses.replace(
        mailer_module.settings, mail_provider="brevo", mail_from="club@test.com", brevo_api_key="k"))
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append((url, json, headers))
        return httpx.Response(401)

    monkeypatch.setattr(mailer_module.httpx, "post", fake_post)
    message = password_recovery_message(email="a@test.com", first_name="Ana", token="abc")
    with pytest.raises(mailer_module.MailDeliveryError):
        mailer_module.BrevoMailer().send(message)
    url, payload, headers = calls[0]
    assert url == mailer_module.BREVO_URL and headers["api-key"] == "k"
    assert payload["to"] == [{"email": "a@test.com", "name": "Ana"}]
