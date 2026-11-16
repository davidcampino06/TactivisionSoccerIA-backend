"""Who a track is, and the tracks that are the same player (accepted links, migration 0029).

A person says who a track is: a shirt number (the squad player who wears it, or only the number),
the referee, or someone outside the game. When the AI suggested that two tracks are one player cut
in two and a person ACCEPTED it, both are one person: whatever is said of one is said of all the
tracks of its chain (12 -> 31 -> 40). The chain comes from track_identities_of (migration 0034),
so it follows only accepted links and never reads other clips.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Detection, Match, Player, TrackLabel, User, VideoAnalysis


@dataclass(frozen=True)
class Identity:
    role: str                   # PLAYER / REFEREE / OTHER
    player_id: str | None = None
    number: int | None = None

    @property
    def known(self) -> bool:
        return self.role != "PLAYER" or self.player_id is not None or self.number is not None

    @property
    def person(self) -> tuple:
        """What says who he is: the role, and for a player his number (or the squad player without one).
        The same number with and without the squad player linked is the same person."""
        if self.role != "PLAYER":
            return (self.role,)
        return (self.role, self.number if self.number is not None else self.player_id)


def merge(identities: list[Identity]) -> Identity | None:
    """The one identity of tracks that are the same player; None when nothing is known.

    Raises ValueError when they were identified as different people."""
    known = [identity for identity in identities if identity.known]
    if len({identity.person for identity in known}) > 1:
        raise ValueError("different people")
    # Prefer the one that also names the squad player.
    return max(known, key=lambda identity: identity.player_id is not None, default=None)


def chain_of(db: Session, analysis_id: str, track_id: int) -> list[int]:
    """The tracks that are the same player as ``track_id`` (itself included), in time order."""
    rows = db.execute(text("SELECT track_id, person_track FROM track_identities_of(:analysis)"),
                      {"analysis": analysis_id}).all()
    person = next((person for track, person in rows if track == track_id), None)
    if person is None:
        return [track_id]
    return [track for track, other in rows if other == person]


def identity_of(db: Session, analysis_id: str, track_id: int) -> Identity:
    label = db.get(TrackLabel, (analysis_id, track_id))
    if label is not None:
        return Identity(label.role)
    player_id, number = (db.query(Detection.player_id, Detection.player_number)
                           .filter(Detection.video_analysis_id == analysis_id, Detection.track_id == track_id)
                           .order_by(Detection.player_number.is_(None), Detection.frame_number).first() or (None, None))
    return Identity("PLAYER", player_id, number)


def player_with_number(db: Session, analysis: VideoAnalysis, number: int | None) -> Player | None:
    """The current squad player who wears ``number`` (one who left the team, INACTIVE, is not matched)."""
    if number is None:
        return None
    team_id = db.get(Match, analysis.video.match_id).team_id
    return (db.query(Player).filter(Player.team_id == team_id, Player.shirt_number == number,
                                    Player.status != "INACTIVE").first())


def apply_identity(db: Session, analysis_id: str, tracks: list[int], identity: Identity, user: User) -> None:
    """Writes the same identity on every track given: the number on their detections, or the label."""
    for track_id in tracks:
        label = db.get(TrackLabel, (analysis_id, track_id))
        detections = db.query(Detection).filter(Detection.video_analysis_id == analysis_id,
                                                Detection.track_id == track_id)
        if identity.role == "PLAYER":
            if label is not None:
                db.delete(label)
            detections.update({Detection.player_id: identity.player_id, Detection.player_number: identity.number},
                              synchronize_session=False)
        else:
            if label is not None:
                label.role, label.labelled_by = identity.role, user.id
            else:
                db.add(TrackLabel(analysis_id=analysis_id, track_id=track_id, role=identity.role, labelled_by=user.id))
            detections.update({Detection.player_id: None, Detection.player_number: None}, synchronize_session=False)
