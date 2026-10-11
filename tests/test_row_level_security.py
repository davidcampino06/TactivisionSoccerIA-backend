"""PostgreSQL Row-Level Security (TactiSoccerIA-db migration 0002), tested at the database level.

These tests skip the API on purpose: they run raw queries WITHOUT any team filter, as if the
backend had a bug. The database itself must still hide and protect the other team's rows.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_team_isolation import world  # noqa: F401  (fixture: two fully populated teams)

import database
import rls
from models import Detection, Match, Player, Team, TacticalPlay, User, Video
from rls import RlsContext

RLS_TABLES = {
    "teams", "players", "player_team_history", "matches", "match_events", "match_formations",
    "tactical_plays", "tactical_play_versions", "match_tactical_plays", "videos", "video_analyses",
    "detections", "tactical_indicators", "ai_recommendations", "recommendation_indicators", "reports",
}


def session_as(context: RlsContext):
    db = database.SessionLocal()
    db.info["rls_context"] = context
    return db


def team_of(email: str) -> tuple[str, str]:
    with rls.mark_system(database.SessionLocal()) as db:
        user = db.query(User).filter(User.email == email).one()
        team = db.query(Team).filter(Team.coach_id == user.id).first()
        return user.id, team.id if team else user.team_id


def test_policies_are_installed():
    with database.engine.connect() as connection:
        enabled = {row[0] for row in connection.execute(text(
            "SELECT relname FROM pg_class WHERE relrowsecurity AND relnamespace = 'public'::regnamespace"))}
        policies = connection.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")).scalar()
        bypass = connection.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'tactivision_app'")).scalar()
    assert RLS_TABLES <= enabled
    assert policies >= 17
    assert bypass is False


def test_request_runs_as_restricted_role(world):
    user_id, team_id = team_of("coach.b@club.com")
    with session_as(RlsContext(user_id=user_id, role="COACH", team_id=team_id)) as db:
        assert db.execute(text("SELECT current_user")).scalar() == "tactivision_app"
        assert db.execute(text("SELECT current_setting('app.current_team_id')")).scalar() == team_id


def test_unfiltered_query_only_returns_own_team(world):
    """Simulated backend bug: SELECT * FROM matches with no WHERE. B still only gets B's rows."""
    user_id, team_b = team_of("coach.b@club.com")
    with session_as(RlsContext(user_id=user_id, role="COACH", team_id=team_b)) as db:
        assert all(match.team_id == team_b for match in db.query(Match).all())
        assert db.get(Match, world["match"]) is None
        assert db.get(Player, world["player"]) is None
        assert db.get(TacticalPlay, world["play"]) is None
        assert db.get(Video, world["video"]) is None
        assert db.query(Detection).count() == 0  # A's detections are invisible
    _, team_a = team_of("coach.a@club.com")
    with session_as(RlsContext(user_id="x", role="COACH", team_id=team_a)) as db:
        assert db.query(Detection).count() > 0
        assert db.get(Match, world["match"]) is not None


def test_anonymous_session_sees_nothing(world):
    with session_as(RlsContext()) as db:
        assert db.query(Team).count() == 0
        assert db.query(Match).count() == 0
        assert db.query(Player).count() == 0
        assert db.query(User).count() > 0  # users has no RLS (needed for login)


def test_cannot_write_into_another_team(world):
    user_id, team_b = team_of("coach.b@club.com")
    db = session_as(RlsContext(user_id=user_id, role="COACH", team_id=team_b))
    try:
        db.add(Player(team_id=world["team"], first_name="Spy", last_name="Player"))
        with pytest.raises(DBAPIError, match="row-level security"):
            db.commit()
    finally:
        db.rollback()
        db.close()
    db = session_as(RlsContext(user_id=user_id, role="COACH", team_id=team_b))
    try:
        changed = db.query(Match).filter(Match.id == world["match"]).update({Match.opponent: "Hacked"})
        deleted = db.query(Match).filter(Match.id == world["match"]).delete()
        db.commit()
        assert (changed, deleted) == (0, 0)  # the row does not exist for B
    finally:
        db.close()


def test_admin_reads_teams_but_no_tactical_rows(world):
    with session_as(RlsContext(user_id="admin", role="ADMINISTRATOR")) as db:
        assert db.query(Team).count() == 2
        assert db.query(Match).count() == 0
        assert db.query(Player).count() == 0


def test_system_session_and_bypass(world):
    with rls.mark_system(database.SessionLocal()) as db:
        assert db.query(Match).count() == 2  # system work sees every team (team A has 2 matches)
    user_id, team_b = team_of("coach.b@club.com")
    with session_as(RlsContext(user_id=user_id, role="COACH", team_id=team_b)) as db:
        db.execute(text("SELECT 1"))  # start the transaction
        assert db.query(Team).count() == 1
        with rls.bypass(db):
            assert db.query(Team).count() == 2
        assert db.query(Team).count() == 1  # back to normal after the bypass block
