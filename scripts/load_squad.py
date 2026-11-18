"""Replace the squad of a team with the players of a squad file (run from your computer).

    python scripts/load_squad.py --api https://YOUR-BACKEND.onrender.com --squad scripts/squad_real_madrid_2026_27.json

Through the same API the app uses: logs in as the coach (the password is asked for, never written,
and is sent encrypted with the server's public key, as the app does; that needs
"pip install cryptography" once), shows the current squad and, after you type REEMPLAZAR, withdraws every current player with a reason
(they stay in the history as withdrawn, as the system requires) and adds the players of the file.
Needs Python 3.10+ and, for a server that only accepts encrypted passwords (production), the
cryptography package.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
from pathlib import Path
from urllib import error, request


def call(base: str, token: str | None, method: str, path: str, body: dict | None = None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(base.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except error.HTTPError as failure:
        raise SystemExit(f"\n{method} {path} -> {failure.code}: {failure.read().decode(errors='replace')[:300]}") from None


def sealed(base: str, password: str) -> str:
    """The password encrypted with the server's public key (RSA-OAEP SHA-256), like the login page."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise SystemExit("Falta el paquete cryptography: pip install cryptography") from None
    key = serialization.load_der_public_key(base64.b64decode(call(base, None, "GET", "/api/auth/public-key")["key"]))
    oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    return "rsa:" + base64.b64encode(key.encrypt(password.encode("utf-8"), oaep)).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True)
    parser.add_argument("--squad", required=True, type=Path)
    parser.add_argument("--email", default="entrenador.demo@tactivision.co")
    args = parser.parse_args()

    squad = json.loads(args.squad.read_text(encoding="utf-8"))
    numbers = [p["shirt_number"] for p in squad["players"]]
    if len(numbers) != len(set(numbers)):
        print("El archivo tiene dorsales repetidos.")
        return 1
    password = sealed(args.api, getpass.getpass(f"Contraseña de {args.email}: "))
    token = call(args.api, None, "POST", "/api/auth/login", {"email": args.email, "password": password})["access_token"]
    team = call(args.api, token, "GET", "/api/teams/mine")
    current = [p for p in call(args.api, token, "GET", f"/api/teams/{team['id']}/players") if p["status"] != "INACTIVE"]
    print(f"\nEquipo «{team['name']}»: {len(current)} jugadores actuales.")
    for player in sorted(current, key=lambda p: (p["shirt_number"] is None, p["shirt_number"] or 0)):
        print(f"   {player['shirt_number'] if player['shirt_number'] is not None else '-':>3}  {player['first_name']} {player['last_name']}")
    print(f"Entrarán {len(squad['players'])} jugadores de {squad.get('team', 'el archivo')} {squad.get('season', '')}.")
    if input("\nEscribe REEMPLAZAR para seguir: ") != "REEMPLAZAR":
        print("No se cambió nada.")
        return 0
    for player in current:
        call(args.api, token, "DELETE", f"/api/players/{player['id']}",
             {"withdrawal_reason": f"Plantilla reemplazada por {squad.get('team', 'otra')} {squad.get('season', '')}".strip()})
    for player in squad["players"]:
        call(args.api, token, "POST", f"/api/teams/{team['id']}/players",
             {key: player[key] for key in ("first_name", "last_name", "shirt_number", "position") if player.get(key) is not None})
        print(f"   + {player['shirt_number']:>2}  {player['first_name']} {player['last_name']}")
    print("\nListo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
