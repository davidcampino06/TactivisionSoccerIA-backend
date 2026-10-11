"""Spanish labels for exported reports (CSV and PDF are read by the coach, not by the API).

The web app has its own copy of these labels in the frontend (i18n/es.ts); exports are generated
on the server, so they need them here too.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

INDICATOR_LABELS = {
    "team_width": "Ancho del equipo",
    "team_length": "Largo del equipo",
    "average_player_distance": "Distancia media entre compañeros",
    "team_compactness_area": "Área de compactación",
    "nearest_teammate_distance": "Distancia al compañero más cercano",
    "defensive_line_position": "Altura de la línea defensiva",
    "defensive_midfield_distance": "Distancia defensa-mediocampo",
    "midfield_attack_distance": "Distancia mediocampo-ataque",
    "largest_line_gap": "Mayor espacio entre líneas",
    "max_zone_concentration": "Concentración máxima en una zona",
    "player_density": "Densidad de jugadores",
    "distribution_third_1": "Distribución en el primer tercio",
    "distribution_third_2": "Distribución en el tercio medio",
    "distribution_third_3": "Distribución en el último tercio",
    "max_zone_numerical_difference": "Diferencia numérica máxima por zona",
    "ball_position_x": "Posición del balón (horizontal)",
    "ball_position_y": "Posición del balón (vertical)",
    "ball_detection_rate": "Cuadros con balón detectado",
}

TEAM_LABELS = {"team_a": "Equipo A", "team_b": "Equipo B", "match": "Partido"}

UNIT_LABELS = {
    "frame_width_ratio": "del ancho de imagen",
    "frame_height_ratio": "del alto de imagen",
    "frame_area_ratio": "del área de imagen",
    "player_ratio": "de los jugadores",
    "frame_ratio": "de los cuadros",
    "players": "jugadores",
    "players_per_frame_area": "jugadores por área de imagen",
}

SEVERITY_LABELS = {"LOW": "Baja", "MEDIUM": "Media", "HIGH": "Alta"}
STATUS_LABELS = {"GENERATED": "Sin revisar", "REVIEWED": "Revisada", "CONFIRMED": "Confirmada", "DISMISSED": "Descartada"}
TREND_LABELS = {"INCREASING": "En aumento", "DECREASING": "En descenso", "STABLE": "Estable",
                "INSUFFICIENT_DATA": "Pocos datos"}
ASSESSMENT_LABELS = {"IMPROVING": "Mejora", "WORSENING": "Empeora", "STABLE": "Estable",
                     "INSUFFICIENT_DATA": "Pocos datos"}
RESULT_LABELS = {"WIN": "Victoria", "DRAW": "Empate", "LOSS": "Derrota"}
REPORT_TYPE_LABELS = {"MATCH": "Reporte de partido", "VIDEO_ANALYSIS": "Reporte de análisis de video",
                      "TEAM_EVOLUTION": "Reporte de evolución del equipo"}

# Match events are free text; common codes are translated and anything else is shown as typed.
EVENT_LABELS = {
    "SHOT": "Remate", "GOAL": "Gol", "PASS": "Pase", "FOUL": "Falta", "CORNER": "Tiro de esquina",
    "OFFSIDE": "Fuera de juego", "YELLOW_CARD": "Tarjeta amarilla", "RED_CARD": "Tarjeta roja",
    "SUBSTITUTION": "Cambio", "SAVE": "Atajada", "RECOVERY": "Recuperación", "LOSS": "Pérdida",
    "PRESSING": "Presión", "COUNTER_ATTACK": "Contraataque", "FREE_KICK": "Tiro libre", "PENALTY": "Penal",
    "BOX": "Área", "MIDFIELD": "Mediocampo", "DEFENSIVE_THIRD": "Tercio defensivo", "ATTACKING_THIRD": "Tercio ofensivo",
    "LEFT_WING": "Banda izquierda", "RIGHT_WING": "Banda derecha", "CENTER": "Centro",
    "SAVED": "Atajado", "MISSED": "Desviado", "BLOCKED": "Bloqueado", "SUCCESS": "Exitoso", "FAILED": "Fallido",
}


def event_label(code: str | None) -> str:
    return "-" if not code else EVENT_LABELS.get(code.upper(), code)


COLOMBIA = timezone(timedelta(hours=-5), "COT")  # Colombia has no daylight saving time


def split_indicator(name: str) -> tuple[str, str]:
    """'team_a.team_width' -> ('Ancho del equipo', 'Equipo A')."""
    prefix, _, rest = name.partition(".")
    if not rest:
        prefix, rest = "match", prefix
    return INDICATOR_LABELS.get(rest, rest.replace("_", " ")), TEAM_LABELS.get(prefix, prefix)


def number(value: float, decimals: int = 2) -> str:
    """Spanish number: decimal comma, dot for thousands, no trailing zeros."""
    text = f"{value:,.{decimals}f}"
    if decimals:
        text = text.rstrip("0").rstrip(".")
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_value(value: float | None, unit: str | None, with_unit: bool = True) -> str:
    """Ratios as percentages ('42 % del ancho de imagen'), the rest as numbers ('6,78 jugadores')."""
    if value is None:
        return "-"
    text = f"{number(value * 100, 0)} %" if unit and unit.endswith("_ratio") else number(value)
    return f"{text} {UNIT_LABELS.get(unit or '', unit or '')}".strip() if with_unit else text


def percent(value: float | None) -> str:
    return "-" if value is None else f"{round(value * 100)} %"


def local_datetime(value: str | None, naive_is_utc: bool) -> str:
    """ISO text -> '10/10/2026 19:47'. Server timestamps are UTC; match dates are already local."""
    if not value:
        return "-"
    moment = datetime.fromisoformat(value)
    if naive_is_utc:
        moment = (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(COLOMBIA)
    return moment.strftime("%d/%m/%Y %H:%M")
