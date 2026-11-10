# De Anza Chess Club — Weekly Puzzle Publisher

Automatically publishes the De Anza Chess Club's weekly chess puzzles to
Instagram ([@deanzachessclub](https://www.instagram.com/deanzachessclub)).

- **Question post:** every Monday and Thursday at **9:00 AM PT** — the puzzle
  position, side to move, and "mate in N", with the caption inviting
  followers to comment their first move.
- **Answer post:** same day at **4:00 PM PT** — the solution lines over the
  *starting* position (never the final mate), so readers can replay it.

Publishing goes through the **Instagram Graph API** from GitHub Actions. No
browser, no manual login, no session cookies to babysit.

## Play online

Play the current puzzle in your browser — no account, no download:

**https://zeppelin567.github.io/chess/#puzzles**

The puzzle mode lives in the [Chess repo](https://github.com/Zeppelin567/chess)
(two-player game + Puzzles tab) and reads `data/queue.json` and
`data/puzzles.csv` from this repo at runtime, so the puzzle on the site
always matches the latest Instagram post. No backend: attempts and solved
state are stored only in the player's own browser.

## Repo layout

```
.
├── render.py                 # renders 1080x1350 question/answer post PNGs
├── requirements.txt          # python-chess, cairosvg, Pillow, requests
├── scripts/
│   └── publish.py            # prepare (render + caption) / post (Graph API)
├── data/
│   ├── puzzles.csv           # puzzle pool: id, theme, rating, side, fen, uci, san
│   └── queue.json            # publish queue (status: queued -> posted -> answered)
├── assets/                   # rendered post images (committed; the API reads them
│                             # from raw.githubusercontent.com)
├── .github/workflows/
│   ├── publish-question.yml  # Mon/Thu 09:00 PT
│   └── publish-answer.yml    # Mon/Thu 16:00 PT
└── docs/
    └── SETUP.md              # one-time setup: Meta app, token, repo secrets
```

## How scheduling works

Each workflow runs on a UTC cron that fires at **both** candidate hours for
the target Pacific time, and `scripts/publish.py` applies a local-time guard
(`America/Los_Angeles`) so only the run that is actually 09:00 / 16:00 local
does anything — this is what makes the schedule survive the PDT/PST change:

| Job | Cron (UTC) | Local time it resolves to |
|---|---|---|
| Question | `0 16,17 * * 1,4` | 09:00 PT, Mon/Thu |
| Answer | `0 23 * * 1,4` and `0 0 * * 2,5` | 16:00 PT, Mon/Thu |

Flow per run: `prepare` picks the next due puzzle from `data/queue.json`,
renders the image and writes `.publish/manifest.json` → the workflow commits
and pushes the image (the Graph API publishes from a public
`raw.githubusercontent.com` URL, so the image **must be on `main` first**)
→ `post` creates the media container, polls until `FINISHED`, publishes it,
fetches the permalink, and only then updates `data/queue.json` → the queue
update is committed and pushed. If any API step fails, the queue is left
untouched and the run fails loudly.

Both workflows can also be run manually from the Actions tab
(`workflow_dispatch`). Manual runs default to **dry run**.

## Secrets

Set these in the repo: Settings → Secrets and variables → Actions.

| Secret | What it is |
|---|---|
| `IG_USER_ID` | The Instagram Business/Creator account's user ID (numeric) |
| `IG_ACCESS_TOKEN` | A long-lived user access token with `instagram_basic` and `instagram_content_publish` |

See [docs/SETUP.md](docs/SETUP.md) for how to obtain them.

## Dry-run behavior

- `DRY_RUN=1`, or missing `IG_USER_ID` / `IG_ACCESS_TOKEN`, makes `post`
  print a `DRY RUN — nothing posted` banner with the manifest and exit 0.
  Nothing is published and `data/queue.json` is not modified.
- `workflow_dispatch` runs default to dry run (`dry_run: true`). Uncheck it
  for a live manual post.

## Local usage

```bash
pip install -r requirements.txt

# Render the next question post (respects the time window; --force to test)
python scripts/publish.py prepare --kind question [--force]

# Dry run the post step (no secrets needed)
DRY_RUN=1 python scripts/publish.py post --kind question

# Live post (needs IG_USER_ID + IG_ACCESS_TOKEN; image must already be
# committed to main, otherwise Instagram cannot fetch it)
IG_USER_ID=... IG_ACCESS_TOKEN=... python scripts/publish.py post --kind question
```

## Cutover note

The queue in this repo (`data/queue.json`) is a **snapshot** of the live
queue taken at scaffolding time. It becomes the live queue only at cutover.
Until the first successful Graph API post, the old system (shared-browser
posting driven by scheduled jobs) stays live — **never edit the live queue
at `~/workspace/goals/international-chess-club-weekly-puzzle-series/hidden_files/puzzle_queue.json`
from this repo**, and do not run both systems at once once cutover happens,
or the same puzzle could be posted twice.
