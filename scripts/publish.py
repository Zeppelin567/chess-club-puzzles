#!/usr/bin/env python3
"""Publish De Anza Chess Club weekly puzzle posts to Instagram via the Graph API.

Two subcommands:

  prepare --kind question|answer
      Pick the next puzzle from data/queue.json, render its image with
      render.py, build the exact caption, and write .publish/manifest.json.
      Exits non-zero with a clear message if nothing is due.

  post --kind question|answer
      Read .publish/manifest.json and publish it through the Instagram
      Graph API, then update data/queue.json on success. With DRY_RUN=1
      or missing secrets it prints a "DRY RUN" banner and exits 0 without
      posting or touching the queue.

Time guard: question posts only run Mon/Thu 09:00-09:59 America/Los_Angeles,
answer posts only Mon/Thu 16:00-16:59. Outside the window, `prepare` prints
"outside window, skipping" and exits 0 (unless --force is given; --force is
for manual testing only, scheduled runs never use it). The guard exists
because the GitHub Actions cron fires at both candidate UTC hours and the
guard picks the one that is 09:00 / 16:00 local across DST changes.

Secrets come from the environment, never from files:
  IG_USER_ID, IG_ACCESS_TOKEN, DRY_RUN=1, GITHUB_REPOSITORY (owner/repo).

IMPORTANT: the image must already be committed to the repo's main branch
before `post` runs, because the Graph API publishes from a public image URL
(https://raw.githubusercontent.com/<owner>/<repo>/main/<image_path>). The
GitHub Actions workflow commits + pushes the rendered asset between `prepare`
and `post`. Running `post` locally right after `prepare` without pushing
will fail at the media-creation step: Instagram cannot fetch an image that
is not yet public.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "data" / "queue.json"
PUZZLES_PATH = ROOT / "data" / "puzzles.csv"
MANIFEST_PATH = ROOT / ".publish" / "manifest.json"
ASSETS_DIR = ROOT / "assets"

LA = ZoneInfo("America/Los_Angeles")
GRAPH_BASE = "https://graph.facebook.com/v21.0"

QUESTION_WINDOW = (9, 10)   # 09:00-09:59 local
ANSWER_WINDOW = (16, 17)    # 16:00-16:59 local


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def today_la() -> str:
    return datetime.now(LA).strftime("%Y-%m-%d")


def in_window(kind: str, now: datetime | None = None) -> bool:
    """True only inside the publish window for this kind (Mon/Thu, local time)."""
    now = now or datetime.now(LA)
    if now.weekday() not in (0, 3):  # Monday, Thursday
        return False
    start, end = QUESTION_WINDOW if kind == "question" else ANSWER_WINDOW
    return start <= now.hour < end


def set_output(name: str, value: str) -> None:
    """Write a step output for GitHub Actions (no-op when run locally)."""
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"{name}={value}\n")


def load_queue() -> list:
    with open(QUEUE_PATH) as f:
        return json.load(f)


def save_queue(queue: list) -> None:
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_puzzles() -> dict:
    puzzles = {}
    with open(PUZZLES_PATH, newline="") as f:
        for row in csv.DictReader(f):
            row["rating"] = int(row["rating"])
            puzzles[row["id"]] = row
    return puzzles


def pair_moves(san: str) -> list:
    """'Qh5+ Kg8 Qh7#' -> ['1. Qh5+   Kg8', '2. Qh7#'] (one full move per line)."""
    moves = san.split()
    lines = []
    for i in range(0, len(moves), 2):
        num = i // 2 + 1
        white = moves[i]
        black = moves[i + 1] if i + 1 < len(moves) else ""
        lines.append(f"{num}. {white}" + (f"   {black}" if black else ""))
    return lines


def question_caption(number: int, side: str, mate_n: str) -> str:
    side_cap = side.capitalize()
    return (
        f"\u265f WEEKLY PUZZLE #{number:03d} \u265f\n"
        f"{side_cap} to move and mate in {mate_n}!\n"
        "Think you've got it? Comment your first move below \U0001f447\n"
        "Full answer drops at 4 PM.\n"
        f"#DeAnzaChessClub #chess #chesspuzzle #matein{mate_n} #deanzacollege"
    )


def answer_caption(number: int, side: str, mate_n: str, san: str) -> str:
    side_cap = side.capitalize()
    moves = "\n".join(pair_moves(san))
    # NOTE: the "tell us your first move" engagement line belongs to the
    # question post ONLY and must never appear in the answer caption.
    return (
        f"\u265f WEEKLY PUZZLE #{number:03d} \u2014 ANSWER \u265f\n"
        f"{side_cap} to move and mate in {mate_n}.\n"
        "\n"
        f"{moves}\n"
        "\n"
        "How did you do? New puzzle drops every Mon & Thu at 9 AM.\n"
        f"#DeAnzaChessClub #chess #chesspuzzle #matein{mate_n} #deanzacollege"
    )


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def cmd_prepare(kind: str, force: bool) -> int:
    if not force and not in_window(kind):
        print(f"outside window, skipping ({kind} runs Mon/Thu "
              f"{QUESTION_WINDOW[0]:02d}:00 or {ANSWER_WINDOW[0]:02d}:00 "
              "America/Los_Angeles)")
        set_output("run", "false")
        return 0

    queue = load_queue()
    puzzles = load_puzzles()

    if kind == "question":
        due = [e for e in queue if e["status"] == "queued"]
        if not due:
            print("ERROR: nothing queued in data/queue.json — "
                  "no puzzle to publish.", file=sys.stderr)
            return 1
        entry = sorted(due, key=lambda e: e["number"])[0]
    else:
        today = today_la()
        due = [e for e in queue
               if e["status"] == "posted" and e.get("posted_at") == today]
        if not due:
            print(f"ERROR: no entry with status 'posted' and "
                  f"posted_at == {today} in data/queue.json — "
                  "no answer to publish.", file=sys.stderr)
            return 1
        entry = sorted(due, key=lambda e: e["number"])[0]

    puzzle = puzzles.get(entry["puzzle_id"])
    if puzzle is None:
        print(f"ERROR: puzzle {entry['puzzle_id']} not found in "
              "data/puzzles.csv.", file=sys.stderr)
        return 1

    number = entry["number"]
    mate_n = entry["theme"].replace("mateIn", "")
    p = {
        "fen": puzzle["fen"],
        "uci": puzzle["uci"],
        "san": puzzle["san"],
        "side": puzzle["side"],
        "theme": puzzle["theme"],
        "rating": puzzle["rating"],
    }

    ASSETS_DIR.mkdir(exist_ok=True)
    if kind == "question":
        image_path = f"assets/puzzle_{number:03d}_en.png"
        render.render_puzzle_post(p, number, str(ROOT / image_path))
        caption = question_caption(number, puzzle["side"], mate_n)
    else:
        image_path = f"assets/answer_{number:03d}_en.png"
        render.render_answer_post(p, number, str(ROOT / image_path))
        caption = answer_caption(number, puzzle["side"], mate_n, puzzle["san"])

    manifest = {
        "number": number,
        "puzzle_id": entry["puzzle_id"],
        "kind": kind,
        "image_path": image_path,
        "caption": caption,
    }
    MANIFEST_PATH.parent.mkdir(exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"prepared #{number:03d} ({entry['puzzle_id']}, {kind}): "
          f"{image_path}")
    print("--- caption ---")
    print(caption)
    set_output("run", "true")
    return 0


# ---------------------------------------------------------------------------
# post (Instagram Graph API)
# ---------------------------------------------------------------------------

def api_error(resp, what: str) -> int:
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    print(f"ERROR: Graph API call failed ({what}): HTTP {resp.status_code}",
          file=sys.stderr)
    print(json.dumps(body, indent=2, ensure_ascii=False), file=sys.stderr)
    print("Queue NOT updated.", file=sys.stderr)
    return 1


def cmd_post(kind: str, owner: str | None, repo: str | None) -> int:
    if not MANIFEST_PATH.exists():
        print("ERROR: .publish/manifest.json not found — run "
              "`prepare` first.", file=sys.stderr)
        return 1
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    dry_run = os.environ.get("DRY_RUN") == "1"
    ig_user_id = os.environ.get("IG_USER_ID")
    token = os.environ.get("IG_ACCESS_TOKEN")

    if dry_run or not ig_user_id or not token:
        reason = ("DRY_RUN=1" if dry_run
                  else "IG_USER_ID / IG_ACCESS_TOKEN not set")
        print("=" * 60)
        print(f"DRY RUN — nothing posted ({reason})")
        print("=" * 60)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    if not owner or not repo:
        gh_repo = os.environ.get("GITHUB_REPOSITORY")
        if gh_repo and "/" in gh_repo:
            owner, repo = gh_repo.split("/", 1)
    if not owner or not repo:
        print("ERROR: owner/repo unknown in live mode — set "
              "GITHUB_REPOSITORY (owner/repo) or pass --owner/--repo.",
              file=sys.stderr)
        return 1

    try:
        import requests
    except ImportError:
        print("ERROR: `requests` is required for live posting "
              "(pip install -r requirements.txt).", file=sys.stderr)
        return 1

    image_url = (f"https://raw.githubusercontent.com/{owner}/{repo}/main/"
                 f"{manifest['image_path']}")

    # 1. Create the media container.
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        params={
            "image_url": image_url,
            "caption": manifest["caption"],
            "access_token": token,
        },
        timeout=30,
    )
    if resp.status_code != 200 or "error" in resp.json():
        return api_error(resp, "create media container")
    creation_id = resp.json()["id"]
    print(f"media container created: {creation_id}")

    # 2. Poll until the container is FINISHED (image processing).
    deadline = time.time() + 60
    while True:
        resp = requests.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        if resp.status_code != 200 or "error" in resp.json():
            return api_error(resp, "check container status")
        status = resp.json().get("status_code")
        print(f"container status: {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            print("ERROR: media container failed processing.",
                  file=sys.stderr)
            print("Queue NOT updated.", file=sys.stderr)
            return 1
        if time.time() > deadline:
            print("ERROR: timed out waiting for container to finish.",
                  file=sys.stderr)
            print("Queue NOT updated.", file=sys.stderr)
            return 1
        time.sleep(5)

    # 3. Publish the container.
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        params={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200 or "error" in resp.json():
        return api_error(resp, "publish media")
    media_id = resp.json()["id"]
    print(f"published media id: {media_id}")

    # 4. Fetch the permalink.
    resp = requests.get(
        f"{GRAPH_BASE}/{media_id}",
        params={"fields": "permalink", "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200 or "error" in resp.json():
        return api_error(resp, "fetch permalink")
    permalink = resp.json().get("permalink", "")
    print(f"permalink: {permalink}")

    # 5. Update the queue — only after a confirmed live publish.
    queue = load_queue()
    for entry in queue:
        if entry["number"] == manifest["number"]:
            if kind == "question":
                entry["status"] = "posted"
                entry["posted_at"] = today_la()
                entry["permalink"] = permalink
            else:
                entry["status"] = "answered"
                entry["answer_permalink"] = permalink
            break
    save_queue(queue)
    print(f"queue updated: #{manifest['number']:03d} -> "
          f"{'posted' if kind == 'question' else 'answered'}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish De Anza Chess Club weekly puzzle posts "
                    "to Instagram via the Graph API.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="render image + caption")
    p_prepare.add_argument("--kind", choices=["question", "answer"],
                           required=True)
    p_prepare.add_argument("--force", action="store_true",
                           help="bypass the time-window guard "
                                "(manual testing only)")

    p_post = sub.add_parser("post", help="publish the prepared manifest")
    p_post.add_argument("--kind", choices=["question", "answer"],
                        required=True)
    p_post.add_argument("--owner", default=None,
                        help="GitHub repo owner (default: GITHUB_REPOSITORY)")
    p_post.add_argument("--repo", default=None,
                        help="GitHub repo name (default: GITHUB_REPOSITORY)")

    args = parser.parse_args(argv)
    if args.command == "prepare":
        return cmd_prepare(args.kind, args.force)
    return cmd_post(args.kind, args.owner, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
