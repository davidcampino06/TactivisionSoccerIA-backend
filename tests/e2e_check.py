"""End-to-end check: Backend -> AI Service -> Backend -> PostgreSQL (real servers running).

    python tests/e2e_check.py path/to/video.mp4 [--backend http://localhost:8000]

Creates a throw-away coach, team and match, uploads the video, starts a REAL analysis and a
SIMULATION analysis, waits for both and prints the stored results.
"""

import argparse
import sys
import time
import uuid

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--max-frames", type=int, default=40)
    args = parser.parse_args()
    api = httpx.Client(base_url=args.backend, timeout=60)

    print("status:", api.get("/api/status").json())
    email = f"e2e-{uuid.uuid4().hex[:8]}@test.com"
    auth = api.post("/api/auth/register", json={"first_name": "E2E", "last_name": "Coach", "email": email,
                                                 "password": "Password123", "role": "COACH"}).json()
    api.headers["Authorization"] = f"Bearer {auth['access_token']}"
    team = api.post("/api/teams", json={"name": "E2E Team"}).json()
    match = api.post(f"/api/teams/{team['id']}/matches",
                     json={"opponent": "E2E Rival", "match_date": "2026-10-01T15:00:00"}).json()
    with open(args.video, "rb") as video_file:
        video = api.post(f"/api/matches/{match['id']}/videos", files={"video": (args.video.split("/")[-1], video_file)}).json()
    print("video:", video["id"], video["file_size"], "bytes")

    results = {}
    for mode in ("REAL_VIDEO_ANALYSIS", "SIMULATION_MODE"):
        started = api.post(f"/api/videos/{video['id']}/analysis",
                           json={"mode": mode, "max_frames": args.max_frames, "frame_stride": 1})
        assert started.status_code == 202, started.text
        analysis_id = started.json()["id"]
        print(f"{mode}: queued (position {started.json()['queue_position']})")
        for _ in range(300):
            status = api.get(f"/api/analyses/{analysis_id}").json()
            if status["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)
        result = api.get(f"/api/analyses/{analysis_id}/result").json()
        results[mode] = result
        print(f"  status={result['analysis']['status']} label={result['label']} model={result['analysis']['model_name']} "
              f"{result['analysis']['model_version']}")
        print(f"  summary={result['summary']}")
        print(f"  indicators={len(result['indicators'])} recommendations={len(result['recommendations'])}")
        print(f"  warning={result['analysis']['warning_message']}")
        if result["recommendations"]:
            top = result["recommendations"][0]
            print(f"  top: {top['title']} | conf={top['confidence']} | {top['evidence']}")
    print("notifications:", [n["event"] for n in api.get("/api/notifications").json()])
    ok = all(r["analysis"]["status"] == "COMPLETED" for r in results.values())
    print("E2E", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
