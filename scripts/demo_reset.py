"""Clean the demo team and load it again with real analyses (run from your computer).

    python scripts/demo_reset.py --api https://YOUR-BACKEND.onrender.com --plan scripts/demo_plan.json --clips "C:\\ruta\\a\\clips"

What it does, through the same API the app uses (so every rule, permission and RLS applies):
  1. Logs in as the demo coach (the password is asked for, never written anywhere).
  2. Lists what the demo team has now: matches (with their videos and analyses), plays, action types and
     reports, and deletes them only after you type BORRAR. Accounts, team and squad are kept.
  3. Creates the matches of the plan with their results, uploads each clip, classifies it and runs a REAL
     analysis of it with YOLO26n frame by frame (nothing is simulated or typed in by hand).
  4. Saves the action types and formations of the plan and draws the plays with them.

Who each player is (shirt numbers, referee) is NOT filled in: a person does it on the video, as in the app.
Needs only Python 3.10+ (standard library). Run it after the backend has a persistent disk, or the
uploaded videos are lost on the next restart.
"""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

DETAIL = {"fast": (5, 120), "full": (3, 300), "slow": (1, 900)}
PITCH_LENGTH, PITCH_WIDTH = 105, 68


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None, data: bytes | None = None,
             content_type: str = "application/json", timeout: float = 120):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            data = json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = content_type
        req = request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except error.HTTPError as failure:
            detail = failure.read().decode(errors="replace")[:300]
            raise SystemExit(f"\n{method} {path} -> {failure.code}: {detail}") from None

    def upload(self, path: str, file: Path, fields: dict[str, str]):
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        kind = mimetypes.guess_type(file.name)[0] or "video/mp4"
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="{file.name}"\r\n'
                     f"Content-Type: {kind}\r\n\r\n".encode() + file.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self.call("POST", path, data=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}",
                         timeout=600)


def formation_tokens(formation: str) -> list[dict]:
    """Same layout as the editor (board.ts formationTokens): goalkeeper plus each line, own half."""
    lines = [int(n) for n in formation.split("-")]
    first, last = 20, 62
    step = (last - first) / (len(lines) - 1) if len(lines) > 1 else 0
    tokens = [{"id": "o1", "side": "own", "x": 5, "y": PITCH_WIDTH / 2, "label": "1", "player_id": None}]
    label = 2
    for index, count in enumerate(lines):
        for slot in range(count):
            tokens.append({"id": f"o{label}", "side": "own", "x": round(first + step * index, 1),
                           "y": round(PITCH_WIDTH * (slot + 1) / (count + 1), 1), "label": str(label), "player_id": None})
            label += 1
    return tokens


def wait_for(api: Api, analysis_id: str) -> dict:
    started = time.time()
    while True:
        state = api.call("GET", f"/api/analyses/{analysis_id}")
        if state["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return state
        print(f"\r      analizando... {time.time() - started:4.0f} s", end="", flush=True)
        time.sleep(4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True, help="URL of the backend, e.g. https://tactivision-backend.onrender.com")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--clips", required=True, type=Path, help="Folder with the clip files named in the plan")
    parser.add_argument("--email", default="entrenador.demo@tactivision.co")
    parser.add_argument("--list-only", action="store_true", help="Only show what the demo team has now")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    missing = [clip["file"] for match in plan["matches"] for clip in match.get("clips", [])
               if not (args.clips / clip["file"]).is_file()]
    if missing:
        print("Faltan estos clips en la carpeta indicada:\n  " + "\n  ".join(missing))
        return 1

    api = Api(args.api)
    password = getpass.getpass(f"Contraseña de {args.email}: ")
    api.token = api.call("POST", "/api/auth/login", {"email": args.email, "password": password})["access_token"]
    team = api.call("GET", "/api/teams/mine")
    team_id = team["id"]
    matches = api.call("GET", f"/api/teams/{team_id}/matches")
    plays = api.call("GET", f"/api/teams/{team_id}/tactical-plays")
    kinds = api.call("GET", f"/api/teams/{team_id}/action-types")
    reports = api.call("GET", f"/api/teams/{team_id}/reports")
    print(f"\nEquipo «{team['name']}» tiene ahora: {len(matches)} partidos (con sus videos y análisis), "
          f"{len(plays)} jugadas, {len(kinds)} tipos de acción y {len(reports)} reportes.")
    for match in sorted(matches, key=lambda m: m["match_date"]):
        print(f"   {match['match_date'][:10]}  vs {match['opponent']}")
    if args.list_only:
        return 0
    if input("\nSe borrará todo eso (se conservan las cuentas, el equipo y la plantilla). Escribe BORRAR para seguir: ") != "BORRAR":
        print("No se borró nada.")
        return 0

    for report in reports:
        api.call("DELETE", f"/api/reports/{report['id']}")
    for play in plays:
        api.call("DELETE", f"/api/tactical-plays/{play['id']}")
    for kind in kinds:
        api.call("DELETE", f"/api/teams/{team_id}/action-types/{kind['id']}")
    for match in matches:
        api.call("DELETE", f"/api/matches/{match['id']}")
    api.call("DELETE", "/api/notifications")
    print("Datos anteriores borrados.\n")

    for name in plan.get("action_types", []):
        api.call("POST", f"/api/teams/{team_id}/action-types", {"name": name})
    known = {f["name"] for f in api.call("GET", "/api/formations")}
    for name in plan.get("formations", []):
        if name not in known:
            api.call("POST", "/api/formations", {"name": name, "description": "Personalizada"})

    created_plays = {}
    for play in plan.get("plays", []):
        board = {"schema": 1, "formation": play["formation"], "notes": play.get("notes", ""),
                 "tokens": formation_tokens(play["formation"]), "arrows": []}
        saved = api.call("POST", f"/api/teams/{team_id}/tactical-plays", {
            "name": play["name"], "action_type": play.get("action_type"), "description": play.get("description"),
            "configuration": board})
        created_plays[play["name"]] = saved["id"]
        print(f"Jugada: {play['name']}")

    stride, max_frames = DETAIL[plan.get("detail", "slow")]
    for item in sorted(plan["matches"], key=lambda m: m["date"]):
        match = api.call("POST", f"/api/teams/{team_id}/matches", {
            "opponent": item["opponent"], "match_date": item["date"], "is_home": item["home"],
            "location": item.get("location"), "status": "SCHEDULED"})
        if item.get("score"):
            api.call("PUT", f"/api/matches/{match['id']}/result", {"home_score": item["score"][0], "away_score": item["score"][1]})
        print(f"\nPartido {item['date'][:10]} vs {item['opponent']}")
        for play_name in item.get("plays", []):
            api.call("POST", f"/api/matches/{match['id']}/tactical-plays", {"tactical_play_id": created_plays[play_name]})
        for clip in item.get("clips", []):
            fields = {key: clip[key] for key in ("situation", "situation_note", "situation_custom")
                      if clip.get(key)}
            video = api.upload(f"/api/matches/{match['id']}/videos", args.clips / clip["file"], fields)
            print(f"   {clip['file']} subido")
            body = {"mode": "REAL_VIDEO_ANALYSIS", "frame_stride": stride, "max_frames": max_frames}
            if item.get("kit_color") or plan.get("kit_color"):
                body["own_kit_color"] = item.get("kit_color") or plan.get("kit_color")
            analysis = api.call("POST", f"/api/videos/{video['id']}/analysis", body)
            state = wait_for(api, analysis["id"])
            print(f"\r      análisis {state['status']}{': ' + state['error_message'] if state.get('error_message') else ''}   ")
    print("\nListo. Ahora identifica a los jugadores en cada video (dorsal, árbitro, externo) desde la app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
