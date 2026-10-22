"""Player availability: why a player is out and the reminder on the day he should be back.

A player can be out for an injury (INJURED), cards (SUSPENDED) or any other reason, personal or
not (UNAVAILABLE). While he is out the coach can write the reason and the expected return date
(TactiSoccerIA-db migration 0016). On that day the bell of the team reminds it once; the status is
never changed automatically, because only the coaching staff knows whether he is really back.

The reminder is created lazily when the team asks for its notifications (the app polls the bell
every few seconds), so no scheduler is needed. Claiming the player with one UPDATE ... RETURNING
makes two polls at the same moment create a single notification.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from models import Player
from services.analysis_events import PLAYER_RETURN_DUE, AnalysisEvent, NotificationCenter
from services.report_labels import COLOMBIA

UNAVAILABLE_STATUSES = frozenset({"INJURED", "SUSPENDED", "UNAVAILABLE"})
STATUS_WORDS = {"INJURED": "lesionado", "SUSPENDED": "suspendido", "UNAVAILABLE": "no disponible"}


def today() -> date:
    """The team's calendar day (Colombia), not the server's UTC day."""
    return datetime.now(COLOMBIA).date()


def clear_availability(player: Player) -> None:
    """The reason and the return date belong to the absence: when it ends they go away."""
    player.availability_note = None
    player.expected_return = None
    player.return_notified_on = None


def return_message(shirt_number: int | None, full_name: str, status: str, note: str | None,
                   expected_return: date, on: date) -> str:
    who = f"#{shirt_number} {full_name}" if shirt_number is not None else full_name
    why = STATUS_WORDS.get(status, "no disponible") + (f": {note}" if note else "")
    when = "Hoy es" if expected_return == on else f"El {expected_return:%d/%m/%Y} era"
    return f"{when} la fecha estimada de regreso de {who} ({why}). Revisa si ya puede jugar y actualiza su estado."


def notify_due_returns(db: Session, team_id: str, on: date | None = None) -> int:
    """Reminds every return of this team due on or before ``on`` that was not reminded yet."""
    on = on or today()
    claimed = db.execute(
        update(Player)
        .where(Player.team_id == team_id, Player.status.in_(UNAVAILABLE_STATUSES),
               Player.expected_return.is_not(None), Player.expected_return <= on,
               or_(Player.return_notified_on.is_(None), Player.return_notified_on != Player.expected_return))
        .values(return_notified_on=Player.expected_return)
        .returning(Player.shirt_number, Player.first_name, Player.last_name, Player.status,
                   Player.availability_note, Player.expected_return)
        .execution_options(synchronize_session=False)
    ).all()
    if not claimed:
        return 0
    db.commit()  # the claim is saved before notifying, so a failure never repeats the reminder
    center = NotificationCenter()
    for shirt, first, last, status, note, expected in claimed:
        center.publish(AnalysisEvent(PLAYER_RETURN_DUE, team_id, None,
                                     return_message(shirt, f"{first} {last}", status, note, expected, on)))
    return len(claimed)
