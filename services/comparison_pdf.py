"""PDF of a comparison of matches: what the comparison page shows, to download and share.

It takes the result of ``compare_matches`` (the same numbers the app draws, nothing recomputed apart
from the texts) and lays it out with the report renderer: the compared matches with their colour, a
chart of the differences between the first and the last match, and one bar chart per indicator.
"""

from __future__ import annotations

from datetime import datetime

from services.report_labels import (
    COLOMBIA, RESULT_LABELS, TEAM_LABELS, UNIT_LABELS, format_value, number, split_indicator,
)
from services.report_pdf import render_pdf

MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
GROUPS = ("team_a", "team_b", "match")
ASSESSMENT = {"BETTER": "mejora", "WORSE": "empeora", "SAME": "sin cambio"}


def _date(iso: str) -> str:
    moment = datetime.fromisoformat(iso)
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}"


def _match_title(match: dict) -> str:
    return f"vs {match['opponent']} · {_date(match['match_date'])}"


def _match_detail(match: dict) -> str:
    parts = []
    if match.get("result"):
        parts.append(f"{RESULT_LABELS.get(match['result'], match['result'])} {match['home_score']}-{match['away_score']}")
    parts.append("Análisis simulado" if match.get("analysis_mode") == "SIMULATION_MODE" else "Análisis de video real")
    issues = match.get("possible_issues", 0)
    parts.append("1 posible problema" if issues == 1 else f"{issues} posibles problemas")
    return " · ".join(parts)


def _delta(value: float, unit: str | None) -> str:
    ratio = bool(unit and unit.endswith("_ratio"))
    shown = number(abs(value) * 100, 0) if ratio else number(abs(value))
    sign = "±" if shown == "0" else "+" if value > 0 else "-"
    return f"{sign}{shown} pts" if ratio else f"{sign}{shown}"


def _group(name: str) -> str:
    prefix = name.split(".", 1)[0]
    return prefix if prefix in ("team_a", "team_b") else "match"


def comparison_blocks(comparison: dict) -> list[dict]:
    matches = comparison["matches"]
    first, last = matches[0], matches[-1]
    blocks: list[dict] = [
        {"kind": "heading", "text": "Partidos comparados"},
        {"kind": "text", "text": "Cada partido tiene el mismo color en todas las gráficas. Están ordenados por fecha: "
                                 "las diferencias se calculan del primero al último."},
        {"kind": "legend", "items": [(_match_title(match), _match_detail(match)) for match in matches]},
    ]
    blocks += [{"kind": "notice", "text": warning} for warning in comparison.get("warnings", [])]

    for group in GROUPS:
        rows = [row for row in comparison["indicators"]
                if _group(row["indicator"]) == group and any(value is not None for value in row["values"])]
        if not rows:
            continue
        blocks.append({"kind": "heading", "text": f"{TEAM_LABELS[group]}: diferencias"})
        changes = [row for row in rows if row.get("change_percent") is not None]
        if changes:
            blocks.append({"kind": "text", "text":
                           f"Cambio de cada indicador entre {_match_title(first)} y {_match_title(last)}, en porcentaje "
                           "del primer valor. A la derecha subió, a la izquierda bajó. Verde: mejora para el equipo; "
                           "rojo: empeora; gris: sin cambio."})
            blocks.append({"kind": "changes", "rows": [
                {"label": split_indicator(row["indicator"])[0], "percent": row["change_percent"],
                 "assessment": row.get("change_assessment"),
                 "text": f"{'+' if row['change_percent'] > 0 else ''}{number(row['change_percent'], 1)} %"}
                for row in sorted(changes, key=lambda row: -abs(row["change_percent"]))]})
        else:
            blocks.append({"kind": "text", "text": "No hay indicadores con valor en el primer y el último partido para medir la diferencia."})

        blocks.append({"kind": "heading", "text": f"{TEAM_LABELS[group]}: indicador por indicador"})
        for row in rows:
            unit = row.get("unit")
            threshold = row.get("threshold")
            side = "por debajo" if row.get("risk_direction") == "below" else "por encima"
            note = UNIT_LABELS.get(unit or "", unit or "")
            if threshold is not None:
                note = f"{note} · posible problema {side} de {format_value(threshold, unit, with_unit=False)} (línea punteada)".strip(" ·")
            difference = row.get("difference_last_vs_first")
            if difference is None:
                difference_text = "Sin dato en el primer o en el último partido: no se calcula la diferencia."
            else:
                verdict = ASSESSMENT.get(row.get("change_assessment") or "", "")
                difference_text = f"Diferencia del primero al último: {_delta(difference, unit)}" + (f" ({verdict})" if verdict else "")
            blocks.append({
                "kind": "bars", "title": split_indicator(row["indicator"])[0], "note": note or " ", "threshold": threshold,
                "assessment": row.get("change_assessment"), "difference": difference_text,
                "bars": [{"label": f"vs {match['opponent']} · {_date(match['match_date']).rsplit(' ', 1)[0]}", "slot": index, "value": row["values"][index],
                          "text": format_value(row["values"][index], unit, with_unit=False),
                          "flag": row["statuses"][index] == "EXCEEDS"}
                         for index, match in enumerate(matches)],
            })
    blocks.append({"kind": "text", "text": "Los valores vienen del último análisis completado de cada partido. El signo «!» marca "
                                           "un valor del lado de riesgo de su umbral. Son indicios para revisar con el cuerpo "
                                           "técnico, no conclusiones."})
    return blocks


def comparison_pdf(team_name: str, comparison: dict) -> bytes:
    matches = comparison["matches"]
    generated = datetime.now(COLOMBIA)
    subtitle = (f"{team_name} · {len(matches)} partidos · generado el {generated.day} {MONTHS[generated.month - 1]} "
                f"{generated.year}, {generated:%H:%M}")
    return render_pdf("Comparación de partidos", subtitle, comparison_blocks(comparison))



