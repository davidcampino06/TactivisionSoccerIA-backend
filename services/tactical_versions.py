"""Tactical play versions: Prototype pattern + Stack.

- Prototype: a new version is a deep CLONE of an existing version (the current one by default)
  with the user's changes applied on top. The coach edits a copy, never the original, so the
  history stays immutable ("Manage Tactical Versions" use case).
- Stack: the version history up to the current version is a LIFO stack; "undo" pops the
  current version and re-activates the one below it.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from sqlalchemy.orm import Session

from data_structures import Stack
from models import TacticalPlay, TacticalPlayVersion, User


class VersionError(ValueError):
    pass


class TacticalConfigurationPrototype:
    def __init__(self, configuration: dict[str, Any]) -> None:
        self._configuration = configuration

    @classmethod
    def from_version(cls, version: TacticalPlayVersion) -> "TacticalConfigurationPrototype":
        return cls(json.loads(version.configuration_data or "{}"))

    def clone(self) -> "TacticalConfigurationPrototype":
        return TacticalConfigurationPrototype(copy.deepcopy(self._configuration))

    def apply_patch(self, patch: dict[str, Any]) -> "TacticalConfigurationPrototype":
        """Recursive merge: nested dicts are merged, other values replaced; None deletes a key."""
        def merge(target: dict, changes: dict) -> None:
            for key, value in changes.items():
                if value is None:
                    target.pop(key, None)
                elif isinstance(value, dict) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = copy.deepcopy(value)
        merge(self._configuration, patch)
        return self

    @property
    def configuration(self) -> dict[str, Any]:
        return self._configuration

    def to_json(self) -> str:
        return json.dumps(self._configuration, ensure_ascii=False)


def versions_of(db: Session, play: TacticalPlay) -> list[TacticalPlayVersion]:
    return (db.query(TacticalPlayVersion)
              .filter(TacticalPlayVersion.tactical_play_id == play.id)
              .order_by(TacticalPlayVersion.version_number).all())


def _activate(versions: list[TacticalPlayVersion], target: TacticalPlayVersion) -> None:
    for version in versions:
        version.is_current = version.id == target.id


def create_version(db: Session, play: TacticalPlay, user: User, patch: dict, base_version_id: str | None) -> TacticalPlayVersion:
    versions = versions_of(db, play)
    if base_version_id:
        base = next((v for v in versions if v.id == base_version_id), None)
        if base is None:
            raise VersionError("Base version does not belong to this tactical play.")
    else:
        base = next((v for v in versions if v.is_current), versions[-1] if versions else None)

    prototype = (TacticalConfigurationPrototype.from_version(base).clone()
                 if base else TacticalConfigurationPrototype({}))
    prototype.apply_patch(patch)

    new_version = TacticalPlayVersion(
        tactical_play_id=play.id,
        created_by=user.id,
        version_number=(versions[-1].version_number + 1) if versions else 1,
        configuration_data=prototype.to_json(),
    )
    db.add(new_version)
    _activate(versions + [new_version], new_version)
    return new_version


def activate_version(db: Session, play: TacticalPlay, version_id: str) -> TacticalPlayVersion:
    versions = versions_of(db, play)
    target = next((v for v in versions if v.id == version_id), None)
    if target is None:
        raise VersionError("Version not found for this tactical play.")
    _activate(versions, target)
    return target


def undo_version(db: Session, play: TacticalPlay) -> TacticalPlayVersion:
    versions = versions_of(db, play)
    current = next((v for v in versions if v.is_current), None)
    if current is None:
        raise VersionError("Tactical play has no current version.")
    history: Stack[TacticalPlayVersion] = Stack(
        [v for v in versions if v.version_number <= current.version_number]
    )
    history.pop()  # current version
    if history.is_empty():
        raise VersionError("There is no previous version to go back to.")
    previous = history.peek()
    _activate(versions, previous)
    return previous
