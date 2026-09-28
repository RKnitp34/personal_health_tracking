# Personal Health Tracking

A simple, self-hosted system for tracking daily fitness and nutrition data.

**Status:** database foundation (Phase 1) + mobile-friendly quick-entry web
app with a personal foods database (Phase 2) + workout history & analytics
(Phase 3) + body/nutrition tracking, a full dashboard, and a calendar view
(Phase 4) + a polished, installable mobile experience (Phase 5) + free
hosting on Render + Neon Postgres (Phase 6). No AI, no authentication, no
Telegram, no other tracking domains yet — those come later.

Add it to your phone's home screen (Safari/Chrome "Add to Home Screen") to
use it like an app — no browser chrome, its own icon, opens straight to
quick-add.

## Stack

- Python 3.11+
- SQLite locally, Postgres (Neon free tier) when hosted — both via the same SQLAlchemy 2.0 layer
- Flask for a minimal server-rendered web UI (no JS framework, no build step)
- Gunicorn as the production WSGI server (hosted only; local dev uses Flask's dev server)
- `python-dotenv` for config
- `pytest` for tests

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional; defaults work out of the box
```

## Run

```bash
python run.py
```

Starts the web app on `http://127.0.0.1:5000` (initializes the database
automatically on first run). To use it from your phone, make sure your
phone is on the same Wi-Fi network as this machine, find this machine's LAN
IP (e.g. `ipconfig getifaddr en0` on macOS), and open
`http://<that-ip>:5000` in your phone's browser.

`python main.py` still works as a standalone DB-init check/CLI if you just
want to verify the database without starting the server.

## Using it

The home page has a single text box. Type a quick entry and hit Add:

| What you want to log | What to type |
|---|---|
| Body weight | `weight 72.4` |
| Weight + body fat % | `weight 72.4 18%` |
| Weight for yesterday | `weight 72.4 yesterday` |
| Workout sets | `bench 60x10 60x8 55x10` |
| Bodyweight sets (no weight) | `pullups x10 x8 x6` |
| Food (one-off, no lookup) | `food chicken salad cal 450` |
| Meal using your foods database | `breakfast 2 eggs 1 banana` |
| Meal with units | `lunch 1 bowl rice 1 bowl dal 100g paneer` |
| Any entry, explicit date | append `on 2026-01-15` |

Manage your personal foods database (name, unit, calories/protein/carbs) at
`/foods` — meal entries look foods up there by name and sum the macros for
you automatically. Unmatched food names are skipped with a message telling
you to add them.

View workout history and analytics at `/exercises` — pick an exercise to
see recent sessions, current vs. previous best, best reps at each weight,
estimated 1RM (Epley formula), weekly volume, and a simple progression
chart.

Set your height and target weight once at `/profile`. Then `/dashboard` is
the main overview, in five cards: **today** (weight/calories/protein/
workout), **body progress** (weight trend chart, BMI, target), **workout
progress** (recent sessions, 7-day volume, current PRs), **nutrition**
(today + 7-day averages), and **recent activity**. It's a responsive
2-column card grid on desktop and a single column on phone.

`/calendar` shows a month grid (weight/calories/protein/carbs per day),
with each day's background shaded by that day's calories relative to the
month's highest day — darker means more logged that day. On phone, each
cell shows just the day number, weight, and calories to stay readable;
protein/carbs appear inline on desktop where there's room. Tap/click any
day to open `/calendar/<date>` — the full breakdown (weight, meals,
workouts, with edit links) for that day. `/body` and `/nutrition` remain
the detailed list/history views behind the dashboard's summary cards.

The "Recent" list below the box shows your last entries; tap **Edit** on any
of them to correct or delete it (workouts can be edited set-by-set or
deleted as a whole).

If you submit something that looks identical to an entry you just added
(same date + values, within 5 minutes), the app asks "Possible duplicate —
add anyway?" instead of silently creating a second row — this catches
accidental double-taps without blocking intentional re-entries.

## Test

```bash
pytest
```

## Deploying for free (Render + Neon Postgres)

The app runs unchanged on either database — SQLite locally, Postgres when
hosted — because everything goes through the same SQLAlchemy layer.

1. **Back up first**: `python scripts/backup_db.py` — copies the live
   SQLite file into `data/backups/` with a timestamp. Safe to re-run
   anytime; it never modifies the original.
2. Create a free [Neon](https://neon.tech) Postgres project and copy its
   connection string.
3. Migrate your data (read-only against SQLite, never modifies it):
   ```bash
   export SOURCE_DB_URL="sqlite:///$(pwd)/data/tracking.db"
   export TARGET_DB_URL="<your Neon connection string>"
   python scripts/migrate_to_postgres.py
   ```
   It creates the tables on Neon, copies every row preserving IDs (so
   foreign keys stay correct), resets Postgres's auto-increment sequences,
   and verifies row counts match before declaring success. It refuses to
   run if either URL doesn't look like the right kind of database.
4. Push this repo to your own GitHub (a personal account, not a work one).
5. Create a Render account, "New Web Service" from that repo (or use the
   included `render.yaml` blueprint). Build command
   `pip install -r requirements.txt`, start command `gunicorn run:app`.
6. In the Render dashboard, set env vars `DATABASE_URL` (the same Neon
   string) and `SECRET_KEY` (a random value) — never in a committed file.
7. Deploy. Render auto-redeploys on every future push to this repo.

**Free-tier behavior to expect**: Render's free web service sleeps after
15 minutes idle — the first request after a gap takes ~30-50s to wake up,
then it's normal speed. Neon's free Postgres scales its compute to zero
after 5 minutes idle but wakes automatically on the next query (no manual
step, unlike some alternatives that fully pause and need a dashboard
click to resume). Both are fine for a personal, single-user app checked
throughout the day — just don't expect instant response after a long gap.

## Project structure

```
.
├── app/
│   ├── config.py     # env/config loading (DATABASE_URL, SECRET_KEY)
│   ├── db.py          # engine/session setup, init_db()
│   ├── models.py      # SQLAlchemy models: BodyMetric, WorkoutSession,
│   │                   # ExerciseSet, FoodLog, Food, Profile
│   ├── parser.py       # regex-based quick-entry parser (no LLM)
│   ├── analytics.py     # deterministic math: volume, PRs, 1RM, BMI,
│   │                      # nutrition totals, progression, SVG chart
│   ├── repository.py   # CRUD + duplicate-detection + analytics queries
│   ├── web.py           # Flask app & routes
│   ├── templates/        # server-rendered HTML (mobile-first, minimal CSS)
│   └── static/            # PWA icon (icon.svg)
├── data/                 # SQLite database file lives here (gitignored)
├── tests/
│   ├── conftest.py       # points tests at a throwaway SQLite file
│   ├── test_models.py
│   ├── test_parser.py
│   ├── test_analytics.py
│   └── test_web.py
├── scripts/
│   ├── backup_db.py      # timestamped copy of the SQLite file
│   └── migrate_to_postgres.py  # one-time SQLite -> Postgres migration + verification
├── main.py               # standalone DB-init check/CLI
├── run.py                # entry point; starts the web app (also the gunicorn target)
├── requirements.txt
├── render.yaml           # Render deploy config (secrets set in the dashboard, not here)
├── .env.example
└── README.md
```

## Schema

- **body_metrics** — one row per day: `date`, `weight_kg`, `body_fat_pct`, `notes`
- **workout_sessions** — one row per workout: `date`, `name`, `notes`
- **exercise_sets** — one row per set, belongs to a `workout_session`: `exercise_name`, `set_number`, `reps`, `weight_kg`, `duration_seconds`, `notes`
- **food_logs** — one row per food entry (one-off or a resolved meal): `date`, `meal_type`, `description`, optional `calories`/`protein_g`/`carbs_g`/`fat_g`, `notes`
- **foods** — your personal food database: `name` (unique), `unit` (`piece`/`bowl`/`spoon`/`cup`/`katori`/`100g`/`100ml`), `calories`, `protein_g`, `carbs_g`
- **profile** — single-row settings: `height_cm`, `target_weight_kg`

All tables have `created_at`/`updated_at` timestamps (UTC, auto-managed).

## Design notes

- **SQLite over Postgres**: this is a single-user local tool — no concurrent
  writers, no network access needed. A file-based DB means zero
  infrastructure to run or back up.
- **No migration tool yet**: `init_db()` just calls `create_all()`, which is
  idempotent and fine while there's no real data to preserve across schema
  changes. Alembic (or similar) will be introduced the first time we need to
  alter a table that already holds data.
- **Regex parser, not an LLM**: the quick-entry formats (`weight X`,
  `exercise WxR WxR`, `food ...`) are small and fixed, so a deterministic
  parser is faster, free, offline-capable, and 100% predictable — no
  hallucinated numbers. An LLM stays out of anything that computes or
  records a number.
- **Server-rendered Flask, no SPA**: a phone browser hitting plain HTML
  forms is the simplest thing that satisfies "fast entry from my phone."
  Avoids a JS build pipeline, a separate API layer, and app-store friction
  entirely.
- **Duplicate detection is a heuristic, not a hard constraint**: it flags an
  exact-match entry created within the last 5 minutes and asks for
  confirmation, rather than enforcing a DB-level uniqueness rule — this
  keeps legitimate same-value re-entries (e.g. logging the same exercise on
  two different days) unaffected.
- **Extensibility**: models are plain SQLAlchemy classes with no coupling to
  fitness/nutrition specifics beyond their own fields, so adding another
  tracking domain (e.g. finance) later is a matter of adding new model
  files, not restructuring what's here.
- **Analytics are plain Python, not an LLM**: volume, PRs, and estimated 1RM
  (Epley formula: `weight x (1 + reps/30)`) are deterministic arithmetic —
  correctness matters more than flexibility here, so there's no room for an
  LLM to introduce error.
- **No JS charting library**: the progression chart is a small inline SVG
  string built by `analytics.render_progression_svg()`. It's a few lines of
  Python instead of a new frontend dependency. The same function powers
  both the workout-progression chart and the weight-trend chart.
- **Profile is a single settings row, not a body_metrics field**: height
  and target weight rarely change and aren't a daily measurement, so they
  live separately rather than being repeated on every weigh-in row.
- **Weekly nutrition average counts every day, not just logged days**: a
  day with no meals logged counts as 0 toward the 7-day average rather
  than being excluded, so the average reflects your actual week.
- **Calendar view, no JS grid library**: built with Python's stdlib
  `calendar.monthcalendar()` for the day layout and a deterministic
  `analytics.calendar_heat_color()` for the per-day shading (intensity =
  that day's calories / the month's highest day, mapped to a lightness
  value) — plain CSS Grid renders it, no dependency added.
- **One `wide` page variant, not a separate framework**: the quick-add page
  stays narrow (best for one-handed phone typing); dashboard/calendar/
  history pages opt into a `wide` body class that only widens and grids
  into 2 columns above 760px, so phone layout is completely unaffected.
- **Calendar day cells stay compact on phone, full detail is a tap away**:
  cramming weight/calories/protein/carbs into a ~40px-wide mobile cell was
  the one genuinely broken part of the old mobile layout. Fix: mobile
  cells show only day number + weight + calories; protein/carbs are
  CSS-hidden below 760px (`.cal-extra`) but every cell now links to a new
  `/calendar/<date>` day page with the complete breakdown and edit links
  — nothing lost, just not crammed into a tiny box.
- **Stat rows use CSS Grid, not flex-wrap**: flex-wrap produced uneven
  3+1/2+2 splits depending on content width. A fixed 2-column grid on
  phone (auto-fit wider columns above 480px) is deterministic and always
  looks balanced.
- **PWA via manifest only, no service worker**: `/manifest.json` + an SVG
  icon + standard meta tags make the app installable to the home screen
  with its own icon and no browser chrome. A service worker (for offline
  caching) was deliberately left out — nothing here needs to work
  offline, so it would be unused complexity.
- **Postgres only when hosted, SQLite otherwise**: no code depends on
  which database is in use — models, parser, repository, and analytics
  are unchanged either way. The one hosted-specific addition,
  `pool_pre_ping=True` on the engine, exists because Neon's free tier
  suspends its compute after 5 minutes idle; without it, the first
  request after a gap would fail on a stale pooled connection instead of
  transparently reconnecting.
- **Migration script is deliberately paranoid**: it refuses to run unless
  `SOURCE_DB_URL` looks like SQLite and `TARGET_DB_URL` looks like
  Postgres (guards against pointing it the wrong way), never writes to
  the source, and verifies row counts on both sides before declaring
  success — for a one-time, hard-to-undo data move, over-checking is
  cheap and mistakes are not.
