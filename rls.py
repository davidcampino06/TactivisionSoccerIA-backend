"""Row-Level Security bridge between the API and PostgreSQL (migration 0002 in TactiSoccerIA-db).

At the beginning of every transaction the session switches to the ``tactivision_app`` role (which
cannot bypass RLS) and tells PostgreSQL who is asking, valid only for that transaction:

    app.current_user_id, app.current_role, app.current_team_id   (request of a logged-in user)
    app.bypass_rls = 'on'                                         (system work, see system_session)

The identity is kept in ``session.info`` because the same Session object is shared by the
dependencies and the endpoint of a request. Enabled with DATABASE_RLS=true; when it is off every
function here is a no-op and the API behaves exactly as before.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace

from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings

APP_ROLE = "tactivision_app"
_INFO_KEY = "rls_context"


@dataclass(frozen=True)
class RlsContext:
    user_id: str = ""
    role: str = ""
    team_id: str = ""
    bypass: bool = False


SYSTEM = RlsContext(role="SYSTEM", bypass=True)


def _apply(connection, context: RlsContext) -> None:
    connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    connection.execute(
        text(
            "SELECT set_config('app.current_user_id', :user_id, true),"
            " set_config('app.current_role', :role, true),"
            " set_config('app.current_team_id', :team_id, true),"
            " set_config('app.bypass_rls', :bypass, true)"
        ),
        {"user_id": context.user_id, "role": context.role, "team_id": context.team_id,
         "bypass": "on" if context.bypass else "off"},
    )


def install(factory: sessionmaker) -> None:
    """Apply the identity at the start of every transaction of sessions created by ``factory``."""

    @event.listens_for(factory, "after_begin")
    def _after_begin(session: Session, _transaction, connection) -> None:
        _apply(connection, session.info.get(_INFO_KEY, RlsContext()))


def set_context(db: Session, context: RlsContext) -> None:
    """Store the identity and apply it right away to the transaction already in progress."""
    if not settings.database_rls:
        return
    db.info[_INFO_KEY] = context
    if db.in_transaction():
        _apply(db.connection(), context)


def identify_user(db: Session, user) -> RlsContext:
    """Identity of a logged-in user. A coach's team is looked up after he is identified,
    because the teams policy lets a coach see the team he owns."""
    from models import Team, UserRole

    context = RlsContext(user_id=user.id, role=user.role,
                         team_id=(user.team_id or "") if user.role == UserRole.ANALYST else "")
    set_context(db, context)
    if user.role == UserRole.COACH and settings.database_rls:
        team_id = db.query(Team.id).filter(Team.coach_id == user.id).scalar()
        context = replace(context, team_id=team_id or "")
        set_context(db, context)
    return context


@contextmanager
def bypass(db: Session) -> Iterator[None]:
    """Temporarily read across teams inside a request (e.g. find a team by its invitation code)."""
    if not settings.database_rls:
        yield
        return
    previous = db.info.get(_INFO_KEY, RlsContext())
    set_context(db, replace(previous, bypass=True))
    try:
        yield
    finally:
        set_context(db, previous)


def mark_system(db: Session) -> Session:
    """Sessions used by background work (analysis worker, restart recovery) see every team."""
    if settings.database_rls:
        db.info[_INFO_KEY] = SYSTEM
    return db
