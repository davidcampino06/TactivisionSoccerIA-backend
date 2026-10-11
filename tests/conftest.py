"""Backend tests run against a real PostgreSQL database built from TactiSoccerIA-db/sql/schema.sql.

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tactivision_test python -m pytest -q
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_REPO = BACKEND_DIR.parent / "TactiSoccerIA-db"
SCHEMA_PATH = Path(os.getenv("SCHEMA_PATH", DB_REPO / "sql" / "schema.sql"))
MIGRATIONS_DIR = Path(os.getenv("MIGRATIONS_DIR", DB_REPO / "migrations"))
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.exit("Set TEST_DATABASE_URL to an EMPTY test database (it will be reset).", returncode=1)

os.environ.update({
    "DATABASE_URL": TEST_DATABASE_URL,
    "JWT_SECRET_KEY": "test-secret-key-only-for-tests-0123456789",
    "ANALYSIS_EXECUTION": "sync",
    "PASSWORD_RESET_EXPOSE_TOKEN": "true",
    "UPLOAD_DIR": tempfile.mkdtemp(prefix="tactivision-uploads-"),
    "AI_SERVICE_URL": "http://127.0.0.1:9",
    # Every test runs with PostgreSQL Row-Level Security turned on (migration 0002).
    "DATABASE_RLS": os.getenv("TEST_DATABASE_RLS", "true"),
})
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import database  # noqa: E402
from main import app  # noqa: E402

TABLES = ("recommendation_indicators, ai_recommendations, tactical_indicators, detections, video_analyses, videos, "
          "reports, match_tactical_plays, tactical_play_versions, tactical_plays, match_formations, formations, "
          "match_events, matches, player_team_history, players, teams, users")


@pytest.fixture(scope="session", autouse=True)
def schema():
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        connection.exec_driver_sql(SCHEMA_PATH.read_text())
        for migration in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            connection.exec_driver_sql(migration.read_text())
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    from services.login_attempts import get_login_attempt_tracker
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE users SET team_id = NULL"))
        connection.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    get_login_attempt_tracker().reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


DEFAULT_PASSWORD = "Tactica#2026"


def register(client, email: str, role: str, password: str = DEFAULT_PASSWORD) -> dict:
    response = client.post("/api/auth/register", json={
        "first_name": "Test", "last_name": role.title(), "email": email, "password": password, "role": role,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "user": body["user"]}


@pytest.fixture
def coach(client):
    return register(client, "coach@test.com", "COACH")


@pytest.fixture
def team(client, coach):
    response = client.post("/api/teams", headers=coach["headers"], json={"name": "Barcelona Juvenil", "city": "Medellin"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def analyst(client, team):
    account = register(client, "analyst@test.com", "ANALYST")
    joined = client.post("/api/teams/join", headers=account["headers"], json={"invitation_code": team["invitation_code"]})
    assert joined.status_code == 200, joined.text
    return account


@pytest.fixture
def admin(client):
    from models import User
    from security import hash_password
    with database.SessionLocal() as db:
        db.add(User(email="admin@test.com", first_name="Admin", last_name="User", role="ADMINISTRATOR",
                    password_hash=hash_password("Gestion#Plataforma26")))
        db.commit()
    token = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "Gestion#Plataforma26"}).json()
    return {"headers": {"Authorization": f"Bearer {token['access_token']}"}}


@pytest.fixture
def match(client, coach, team):
    response = client.post(f"/api/teams/{team['id']}/matches", headers=coach["headers"],
                           json={"opponent": "Nacional", "match_date": "2026-09-01T15:00:00", "is_home": True})
    assert response.status_code == 201, response.text
    return response.json()
