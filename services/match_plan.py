"""Match plan: one page per match with only what a person confirmed and what the staff entered.

    match       rival, date, home or away, venue
    squad       available players by position; the unavailable ones with their reason, their expected
                return and whether that return falls before the match
    plays       tactical plays linked to this match (current version: formation and notes)
    to_correct  possible problems CONFIRMED by a person in the last analysed matches before this one,
                of our team (the analysis knows which detected team is ours) or of the whole match,
                grouped when the same problem appeared in several matches, with the staff's notes
    to_keep     strengths CONFIRMED by a person in the same analyses, grouped the same way
    left_out    how many problems and strengths of those matches are still unreviewed (not shown)

Nothing here is computed by the AI: the plan only orders what is stored. Unreviewed or dismissed
items never reach it.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from models import (
    AIRecommendation, AnalysisStrength, Match, MatchTacticalPlay, Player, RecommendationIndicator, TacticalIndicator,
    TacticalPlay, TacticalPlayVersion, Video, VideoAnalysis,
)
from services import report_labels as labels
from services.match_timeline import analysed_matches
from services.player_returns import UNAVAILABLE_STATUSES
from services.review_notes import notes_of

LOOKBACK_MATCHES = 3
POSITIONS = ("GOALKEEPER", "DEFENDER", "MIDFIELDER", "FORWARD")
POSITION_LABELS = {"GOALKEEPER": "Porteros", "DEFENDER": "Defensas", "MIDFIELDER": "Centrocampistas",
                   "FORWARD": "Delanteros", None: "Sin posición"}
STATUS_LABELS = {"INJURED": "Lesionado", "SUSPENDED": "Suspendido", "UNAVAILABLE": "No disponible"}
ROLE_LABELS = {"COACH": "entrenador", "ANALYST": "analista"}
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
ISSUE_PREFIX = "Posible problema táctico: "


def _player(player: Player) -> dict:
    return {"id": player.id, "shirt_number": player.shirt_number, "name": f"{player.first_name} {player.last_name}",
            "position": player.position}


def _squad(db: Session, match: Match) -> dict:
    players = (db.query(Player).filter(Player.team_id == match.team_id, Player.status != "INACTIVE")
                 .order_by(Player.shirt_number.is_(None), Player.shirt_number, Player.last_name).all())
    match_day = match.match_date.date()
    available = [p for p in players if p.status == "ACTIVE"]
    groups = []
    for position in (*POSITIONS, None):
        members = [_player(p) for p in available
                   if (p.position if p.position in POSITIONS else None) == position]
        if members:
            groups.append({"position": position, "label": POSITION_LABELS[position], "players": members})
    unavailable = [
        {**_player(p), "status": p.status, "reason": p.availability_note,
         "expected_return": p.expected_return.isoformat() if p.expected_return else None,
         "back_before_match": bool(p.expected_return and p.expected_return <= match_day)}
        for p in players if p.status in UNAVAILABLE_STATUSES
    ]
    return {"available_count": len(available), "groups": groups, "unavailable": unavailable}


def _plays(db: Session, match: Match) -> list[dict]:
    rows = (db.query(TacticalPlay).join(MatchTacticalPlay, MatchTacticalPlay.tactical_play_id == TacticalPlay.id)
              .filter(MatchTacticalPlay.match_id == match.id).order_by(TacticalPlay.name).all())
    plays = []
    for play in rows:
        version = (db.query(TacticalPlayVersion)
                     .filter(TacticalPlayVersion.tactical_play_id == play.id, TacticalPlayVersion.is_current.is_(True))
                     .first())
        try:
            configuration = json.loads(version.configuration_data) if version else {}
        except ValueError:
            configuration = {}
        plays.append({"id": play.id, "name": play.name, "action_type": play.action_type,
                      "description": play.description, "formation": configuration.get("formation"),
                      "notes": configuration.get("notes") or None,
                      "version": version.version_number if version else None})
    return plays


def _previous_matches(db: Session, match: Match) -> list[dict]:
    """The last analysed matches played before this one, newest first."""
    before = [m for m in analysed_matches(db, match.team_id)
              if m["match_id"] != match.id and m["match_date"] < match.match_date.isoformat()]
    return sorted(before, key=lambda m: m["match_date"], reverse=True)[:LOOKBACK_MATCHES]


def _ours(team: str | None, own_team: str | None) -> bool:
    """With the user's team known, only its items and match-level ones; unknown: all (labelled)."""
    return own_team is None or team in (own_team, "MATCH")


def _occurrence(match: dict, analysis: VideoAnalysis | None, team: str | None) -> dict:
    return {"match_id": match["match_id"], "opponent": match["opponent"], "match_date": match["match_date"],
            "analysis_id": analysis.id if analysis else None, "team": team,
            "team_known": bool(analysis and analysis.own_team)}


def _to_correct(db: Session, previous: list[dict]) -> tuple[list[dict], int]:
    by_match = {m["match_id"]: m for m in previous}
    if not by_match:
        return [], 0
    recommendations = db.query(AIRecommendation).filter(AIRecommendation.match_id.in_(by_match)).all()
    analysis_ids = dict(
        db.query(RecommendationIndicator.recommendation_id, TacticalIndicator.video_analysis_id)
          .join(TacticalIndicator, TacticalIndicator.id == RecommendationIndicator.indicator_id)
          .filter(RecommendationIndicator.recommendation_id.in_([r.id for r in recommendations])).all()
    ) if recommendations else {}
    analyses = {a.id: a for a in db.query(VideoAnalysis).filter(VideoAnalysis.id.in_(set(analysis_ids.values()))).all()}
    confirmed, unreviewed = [], 0
    for recommendation in recommendations:
        analysis = analyses.get(analysis_ids.get(recommendation.id))
        if not _ours(recommendation.team, analysis.own_team if analysis else None):
            continue
        if recommendation.status == "CONFIRMED":
            confirmed.append((recommendation, analysis))
        elif recommendation.status in ("GENERATED", "REVIEWED"):
            unreviewed += 1
    notes = notes_of(db, [r.id for r, _ in confirmed])
    grouped: dict[str, dict] = {}
    for recommendation, analysis in confirmed:
        match = by_match[recommendation.match_id]
        item = grouped.setdefault(recommendation.title, {
            "title": recommendation.title.removeprefix(ISSUE_PREFIX).capitalize(),
            "recommendation": recommendation.description, "severity": recommendation.severity,
            "occurrences": [], "notes": []})
        if SEVERITY_ORDER.get(recommendation.severity, 3) < SEVERITY_ORDER.get(item["severity"], 3):
            item["severity"] = recommendation.severity
        item["occurrences"].append({**_occurrence(match, analysis, recommendation.team),
                                    "confidence": float(recommendation.confidence)})
        for note in notes.get(recommendation.id, []):
            item["notes"].append({"author": note.author_name, "role": ROLE_LABELS.get(note.author_role or ""),
                                  "text": note.text, "created_at": note.created_at.isoformat(),
                                  "opponent": match["opponent"]})
    items = sorted(grouped.values(), key=lambda i: (-len(i["occurrences"]), SEVERITY_ORDER.get(i["severity"], 3)))
    for item in items:
        item["notes"].sort(key=lambda note: note["created_at"])
    return items, unreviewed


def _to_keep(db: Session, previous: list[dict]) -> tuple[list[dict], int]:
    by_match = {m["match_id"]: m for m in previous}
    if not by_match:
        return [], 0
    rows = (db.query(AnalysisStrength, VideoAnalysis, Video.match_id)
              .join(VideoAnalysis, VideoAnalysis.id == AnalysisStrength.analysis_id)
              .join(Video, Video.id == VideoAnalysis.video_id)
              .filter(Video.match_id.in_(by_match)).all())
    grouped: dict[str, dict] = {}
    unreviewed = 0
    for strength, analysis, match_id in rows:
        if not _ours(strength.team, analysis.own_team):
            continue
        if strength.status == "GENERATED":
            unreviewed += 1
            continue
        if strength.status != "CONFIRMED":
            continue
        try:
            explanation = json.loads(strength.explanation or "{}") or {}
        except ValueError:
            explanation = {}
        item = grouped.setdefault(strength.code, {"title": strength.title, "meaning": explanation.get("meaning"),
                                                  "keep": explanation.get("keep"), "occurrences": []})
        item["occurrences"].append({**_occurrence(by_match[match_id], analysis, strength.team),
                                    "confidence": float(strength.confidence)})
    return sorted(grouped.values(), key=lambda i: -len(i["occurrences"])), unreviewed


def match_plan(db: Session, match: Match) -> dict:
    previous = _previous_matches(db, match)
    to_correct, open_problems = _to_correct(db, previous)
    to_keep, open_strengths = _to_keep(db, previous)
    return {
        "match": {"id": match.id, "opponent": match.opponent, "match_date": match.match_date.isoformat(),
                  "is_home": match.is_home, "location": match.location, "status": match.status},
        "squad": _squad(db, match),
        "plays": _plays(db, match),
        "based_on": previous,
        "to_correct": to_correct,
        "to_keep": to_keep,
        "left_out": {"problems": open_problems, "strengths": open_strengths},
    }


# ---------------------------------------------------------------------------------------------- PDF
def _short_date(value: str) -> str:
    return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")


def _player_line(player: dict) -> str:
    return f"{player['shirt_number']} {player['name']}" if player["shirt_number"] is not None else player["name"]


def plan_blocks(plan: dict) -> list[dict]:
    """The plan as the format-neutral blocks that services/report_pdf.py draws."""
    match = plan["match"]
    blocks: list[dict] = [{"kind": "facts", "items": [
        ("Rival", match["opponent"]),
        ("Fecha", labels.local_datetime(match["match_date"], naive_is_utc=False)),
        ("Condición", "Local" if match["is_home"] else "Visitante"),
        ("Lugar", match["location"] or "-"),
    ]}, {"kind": "notice", "text": "Solo aparece lo que una persona del cuerpo técnico confirmó y los datos que el "
                                   "equipo registró. Lo que la IA propuso sin revisar no se incluye."}]

    squad = plan["squad"]
    blocks.append({"kind": "heading", "text": f"Disponibles ({squad['available_count']})"})
    if squad["groups"]:
        blocks.append({"kind": "table", "columns": ["Posición", "Jugadores"], "widths": [1.4, 5],
                       "rows": [[g["label"], ", ".join(_player_line(p) for p in g["players"])] for g in squad["groups"]]})
    else:
        blocks.append({"kind": "text", "text": "No hay jugadores disponibles registrados."})
    if squad["unavailable"]:
        rows = []
        for p in squad["unavailable"]:
            back = _short_date(p["expected_return"]) if p["expected_return"] else "-"
            if p["back_before_match"]:
                back += " (antes del partido: revisar)"
            rows.append([_player_line(p), STATUS_LABELS.get(p["status"], p["status"]), p["reason"] or "-", back])
        blocks += [{"kind": "heading", "text": f"No disponibles ({len(squad['unavailable'])})"},
                   {"kind": "table", "columns": ["Jugador", "Estado", "Motivo", "Regreso estimado"],
                    "widths": [2, 1.3, 3, 2], "rows": rows}]

    blocks.append({"kind": "heading", "text": "Jugadas para este partido"})
    if plan["plays"]:
        blocks.append({"kind": "table", "columns": ["Jugada", "Formación", "Notas"], "widths": [2.2, 1, 4],
                       "rows": [[p["name"], p["formation"] or "-", p["notes"] or p["description"] or "-"]
                                for p in plan["plays"]]})
    else:
        blocks.append({"kind": "text", "text": "No hay jugadas de la pizarra vinculadas a este partido."})

    based = plan["based_on"]
    source = ", ".join(f"vs {m['opponent']} ({_short_date(m['match_date'])})" for m in based) or "ninguno"
    blocks.append({"kind": "heading", "text": "A corregir"})
    blocks.append({"kind": "text", "text": f"Problemas confirmados en los últimos partidos analizados: {source}."})
    if not plan["to_correct"]:
        blocks.append({"kind": "text", "text": "Ningún problema confirmado en esos partidos."})
    for item in plan["to_correct"]:
        seen = ", ".join(f"vs {o['opponent']}" for o in item["occurrences"])
        details = [("Recomendación", item["recommendation"])]
        details += [(f"{n['author'] or 'Usuario eliminado'} ({n['role'] or '-'}, vs {n['opponent']})", n["text"])
                    for n in item["notes"]]
        blocks.append({"kind": "issue", "severity": item["severity"], "title": item["title"],
                       "meta": f"Severidad {labels.SEVERITY_LABELS.get(item['severity'], item['severity']).lower()}"
                               f" · visto en {len(item['occurrences'])} de {len(based)} partidos ({seen})",
                       "details": details})

    blocks.append({"kind": "heading", "text": "A mantener"})
    if not plan["to_keep"]:
        blocks.append({"kind": "text", "text": "Ninguna fortaleza confirmada en esos partidos."})
    for item in plan["to_keep"]:
        seen = ", ".join(f"vs {o['opponent']}" for o in item["occurrences"])
        blocks.append({"kind": "issue", "severity": "STRENGTH", "title": item["title"],
                       "meta": f"Confirmada en {len(item['occurrences'])} de {len(based)} partidos ({seen})",
                       "details": [("Qué significa", item["meaning"] or "-"), ("Cómo mantenerlo", item["keep"] or "-")]})

    left = plan["left_out"]
    if left["problems"] or left["strengths"]:
        blocks.append({"kind": "notice", "text": f"Sin revisar y por eso fuera del plan: {left['problems']} posibles "
                                                 f"problemas y {left['strengths']} fortalezas."})
    return blocks
