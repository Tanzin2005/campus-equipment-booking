# Campus Equipment Booking

A full-stack application for finding campus equipment, reserving a time slot, and managing bookings. Built with **FastAPI, SQLAlchemy, SQLite/PostgreSQL, and a responsive JavaScript frontend**.

## Features

- Equipment library with search, category filters, and availability for a selected time.
- Registration and sign-in with Argon2 password hashing and revocable cookie sessions.
- Student-owned reservations: users see and cancel their own bookings.
- Conflict prevention for overlapping reservations; back-to-back bookings are allowed.
- Cancellation that immediately releases the time slot while preserving history.
- Administrator controls to add, edit, and take equipment offline, and manage all reservations.
- UTC timestamp storage with dates displayed in each browser's timezone.
- Database migrations, legacy-data preservation, Docker configuration, and SQLite/PostgreSQL CI jobs.
- Automated tests for authentication, permissions, booking rules, concurrency, and migrations.

The app starts with **six sample equipment items** on a fresh database. Administrators can replace them with their own inventory. This repository is a portfolio application, not a claim of deployment at an actual institution.

## Quick start on Windows

Install **Python 3.12 or newer**. Download or clone this repository and open the folder containing `requirements.txt`.

**Double-click `RUN_WINDOWS.bat`.** It creates a local virtual environment, installs dependencies, and starts the server. Once startup completes, open:

**http://127.0.0.1:8000**

Select **Sign in → Create account** to register. Use the same hostname consistently; cookies for `localhost` and `127.0.0.1` are separate.

Manual commands, from the project folder:

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

If you are updating the original starter, see [UPGRADE.md](UPGRADE.md). The new launcher creates `.venv` inside this project, independent of the old parent-folder environment.

## Linux / macOS

```bash
git clone https://github.com/Tanzin2005/campus-equipment-booking.git
cd campus-equipment-booking
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. Stop the server with `Ctrl+C`. SQLite data is stored in `data/bookings.db` and survives restarts.

## Create an administrator

Public registration always creates a student account. There are no default administrator credentials.

After registering your own account, run this in another terminal from the project folder:

```bat
.venv\Scripts\python.exe -m app.manage promote --email your-email@example.com
```

Refresh the browser. **Administration** will appear in the navigation.

Alternatively, create a separate administrator account using interactive prompts:

```bat
.venv\Scripts\python.exe -m app.manage create-admin
```

For Linux/macOS, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

## Docker

Run the SQLite version:

```bash
docker compose up --build
```

Visit **http://127.0.0.1:8000**. The named volume preserves data. To promote an account created in the application:

```bash
docker compose exec app python -m app.manage promote --email your-email@example.com
```

### PostgreSQL

1. Copy `.env.example` to `.env`.
2. Generate a random password with `python -c "import secrets; print(secrets.token_hex(24))"`.
3. Set `POSTGRES_PASSWORD` in `.env` to that hexadecimal value.
4. Start the PostgreSQL configuration:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml up --build
```

Use hexadecimal characters for this Compose password because it is interpolated into a connection URL. An externally supplied `DATABASE_URL` must percent-encode reserved characters in credentials.

The PostgreSQL database starts empty; selecting PostgreSQL does not transfer existing SQLite records. The app's migration account needs permission to install `btree_gist`, or an operator must install it first. PostgreSQL's exclusion constraint rejects overlapping confirmed reservations even when inserts bypass the API.

## Reservation rules

- Start time must be in the future; end time must be later than start time.
- A reservation can last up to 24 hours.
- Overlap is checked per individual equipment item.
- A student may cancel a reservation before it starts; an administrator can also cancel active reservations.
- Cancellation is idempotent and preserves the record.
- Equipment cannot be taken offline while it has confirmed reservations that have not ended. Cancel them first.
- The user's ID and name come from the authenticated session, not request-body fields.

## API

Interactive documentation is available at **http://127.0.0.1:8000/docs**.

| Method | Endpoint | Access / purpose |
| --- | --- | --- |
| GET | `/equipment` | Public catalog; search, category, interval, and pagination filters |
| GET | `/equipment/{id}/schedule` | Public reserved intervals; excludes names and booking IDs |
| POST | `/auth/register` | Create a student account and start a session |
| POST | `/auth/login` | Start a session |
| GET | `/auth/me` | Current account and CSRF token |
| POST | `/auth/logout` | Revoke the current session |
| POST | `/bookings` | Reserve equipment as the signed-in user |
| GET | `/bookings` | Paginated own reservations; `view=upcoming`, `past`, `cancelled`, or `all` |
| GET | `/bookings/{id}` | Owner or administrator |
| POST | `/bookings/{id}/cancel` | Owner or administrator |
| GET / POST | `/admin/equipment` | Administrator inventory listing / creation |
| PUT | `/admin/equipment/{id}` | Administrator inventory editing |
| GET | `/health` | Application and database health |

Administrators can pass `all_users=true` to `GET /bookings`. A student's attempt to use that option returns 403.

### Authenticated requests

The frontend handles sessions and CSRF automatically. For manual use through `/docs`:

1. Call `/auth/login` or `/auth/register` with JSON.
2. Copy the returned `csrf_token`.
3. Supply it in the `X-CSRF-Token` header field for protected writes. The browser sends the session cookie automatically.

Example booking body (change the timestamps to a future day):

```json
{
  "equipment_id": 1,
  "start_at": "2026-10-01T10:00:00+05:30",
  "end_at": "2026-10-01T11:00:00+05:30",
  "purpose": "Control systems lab project"
}
```

A successful booking returns 201. Overlaps return 409; invalid input returns 422. Unauthenticated requests return 401. Accessing another student's reservation returns 404.

## Tests and CI

```bat
.venv\Scripts\python.exe -m pytest -q
```

The suite creates isolated databases. Set `TEST_DATABASE_URL` to run against PostgreSQL; the test database account must be able to create/drop schemas and install `btree_gist`. Each test uses a unique schema and removes it afterward. **Use a dedicated test database.**

GitHub Actions defines SQLite jobs for Python 3.12/3.13 and a PostgreSQL job, plus JavaScript syntax validation. CI runs after these files are pushed; including the workflow does not imply that a remote run has passed. See [the validation record](docs/VALIDATION.md) for what was checked during this release.

## Architecture

| Path | Responsibility |
| --- | --- |
| `app/main.py` | HTTP routes, permissions, reservation transactions, and static serving |
| `app/security.py` | Password hashing, sessions, CSRF checks, and login/registration throttling |
| `app/schemas.py` | Request and response validation |
| `app/models.py` | SQLAlchemy table definitions |
| `app/database.py` | Engine configuration, transaction boundaries, migrations, and legacy backup |
| `app/static/` | Responsive frontend; no Node build or separate frontend server required |
| `app/manage.py` | Operator-only migration and administrator commands |
| `migrations/` | Alembic schema history |
| `tests/` | Behavioral API tests |

SQLite acquires a database write lock before checking and inserting reservations. PostgreSQL locks the equipment row and also enforces a GiST exclusion constraint over the reserved time interval. [More design details](docs/ARCHITECTURE.md).

## Deployment configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Unset | PostgreSQL or explicit SQLAlchemy database URL |
| `BOOKING_DB` | `data/bookings.db` under the project | SQLite file when `DATABASE_URL` is unset |
| `COOKIE_SECURE` | `false` | Set `true` when serving through HTTPS |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | Comma-separated allowed hostnames |
| `APP_ORIGIN` | Request origin | Explicit external origin when behind a trusted reverse proxy |
| `AUTO_MIGRATE` | `true` | Set `false` after running migrations separately during deployment |

Local Python commands read process environment variables; `.env` is consumed by Docker Compose, not loaded automatically by Python.

For external hosting, use a persistent database, HTTPS, secure cookies, and your actual hostname/origin. Configure Uvicorn's proxy trust for your reverse proxy only. Run `python -m app.manage migrate` before starting multiple workers with `AUTO_MIGRATE=false`. The Docker image runs as a non-root user.

The application includes same-origin checks, CSRF tokens, HttpOnly/SameSite cookies, server-side session expiry, and database-backed authentication rate limits. Email verification and self-service password recovery are not implemented. This is a completed portfolio MVP; it has not undergone a production security audit or capacity benchmark.

## Development

Developed with AI assistance and maintained by Tanzin Jayang. Feature descriptions reflect implemented behavior; deployment counts, real users, and performance claims should only be added after measurement.
