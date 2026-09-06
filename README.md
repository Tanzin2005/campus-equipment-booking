# Campus Equipment Booking

A FastAPI backend for reserving individual pieces of campus equipment, such as
oscilloscopes, Arduino kits, and projectors. Built as a guided resume project.

## Current milestone: working reservation API

- Lists three sample equipment items.
- Stores reservations in SQLite so they survive a restart.
- Rejects overlapping reservations, including concurrent API requests.
- Allows back-to-back reservations and simultaneous bookings of different items.
- Requires future, timezone-aware timestamps and normalizes them to UTC.
- Lists reservations with equipment filtering and pagination.
- Includes automated API tests and interactive API documentation.

This is a local learning prototype. It has no login or ownership checks yet;
names are unverified input and all reservations are readable. Use fictional data
and run locally until the authentication milestone is complete.

## Run on Windows PowerShell

Install Python 3.12 or newer. Extract the zip, open the `campus-booking` folder
in VS Code, then open a PowerShell terminal in that folder.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

These commands use the virtual environment directly, so you do not need to
activate it or change PowerShell's execution policy. If `py` is unavailable but
`python --version` works, use `python -m venv .venv` for the first command.

Open http://127.0.0.1:8000/docs in your browser.
Stop the server with Ctrl+C. Data is created in `data/bookings.db`.

Linux/macOS equivalents:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

## First hands-on task

1. In `/docs`, expand `GET /equipment`, click **Try it out**, then **Execute**.
2. Expand `POST /bookings` and submit the example below, changing both dates
   to a future day. `+05:30` specifies Indian Standard Time.
3. Submit it again. You should receive HTTP **409 Conflict**.
4. Change the time to 11:00–12:00. It should succeed with **201 Created**.

```json
{
  "equipment_id": 1,
  "student_name": "Demo Student",
  "start_at": "2026-10-01T10:00:00+05:30",
  "end_at": "2026-10-01T11:00:00+05:30"
}
```

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | App information |
| GET | `/equipment` | List equipment |
| POST | `/bookings` | Reserve one item |
| GET | `/bookings?equipment_id=1&limit=20&offset=0` | Filter and page reservations |

Validation failures return 422, missing equipment returns 404, and conflicting
reservations return 409. All returned reservation timestamps are UTC.

## Understand the code

Read `app/main.py` first. A route connects an HTTP request to a Python function.
`BookingRequest` describes and validates the JSON sent by the caller.
`database.py` creates tables and manages database connections and transactions.
SQL parameters (`?`) pass values separately from SQL command text.

Two intervals overlap when:

```text
existing_start < requested_end AND existing_end > requested_start
```

Strict inequalities allow a booking ending at 11:00 and another starting at
11:00. `BEGIN IMMEDIATE` takes SQLite's write lock before checking for a
conflict, keeping the availability check and insertion in one transaction.
All reservation writes must go through this path. The time index improves
lookup; it does not independently enforce the no-overlap rule.

SQLite serializes writers. This is suitable for this local prototype; high
load can exhaust the lock wait timeout. A later PostgreSQL version should
enforce overlap prevention with a database exclusion constraint rather than
copying this SQLite locking strategy unchanged.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover overlapping intervals, adjacent bookings, separate equipment,
invalid input, UTC equivalence, persistence, filtering, and four simultaneous
attempts to reserve the same slot. Tests use temporary databases.

## Development roadmap

1. **Understand this milestone:** run it, explain each endpoint, reproduce a conflict.
2. **Identity and permissions:** users, hashed passwords, login, own reservations,
   administrator-only equipment management. Derive booking ownership from the
   logged-in user, never from a caller-supplied user ID.
3. **Booking lifecycle:** cancellation, availability search, maintenance periods,
   and tests showing cancellation frees a slot.
4. **PostgreSQL:** schema migrations, database-enforced conflict prevention,
   and concurrent booking tests on PostgreSQL.
5. **Portfolio delivery:** a usable frontend, Docker, CI, deployment, architecture
   explanation, and measured performance under a documented workload.

Complete one milestone at a time. The frontend and deployment are future work.

## Resume evidence

After you run and understand this milestone, an accurate description is:

> Built a FastAPI and SQLite equipment reservation API with timestamp validation,
> transaction-protected overlap checks, and automated tests for concurrent bookings.

Only add authentication, PostgreSQL, deployment, user counts, or performance
numbers after implementing or measuring them. Keep a record of design decisions
and test outputs so you can explain the project in an interview.

## References

- FastAPI database tutorial: https://fastapi.tiangolo.com/tutorial/sql-databases/
- FastAPI testing guide: https://fastapi.tiangolo.com/tutorial/testing/
- Python sqlite3 documentation: https://docs.python.org/3/library/sqlite3.html
