# Campus Equipment Booking

A FastAPI backend for reserving campus equipment such as oscilloscopes, Arduino kits, and projectors. Reservations persist in SQLite, and overlapping bookings for the same item are rejected.

**Status:** Local prototype. Authentication, booking ownership, cancellation, and a frontend are planned. Use sample data: the current API accepts unverified student names and exposes all bookings.

## Features

- Browse three sample equipment items.
- Create reservations with validated, timezone-aware start and end times.
- Prevent overlapping reservations, including simultaneous requests through the API.
- Allow back-to-back reservations and concurrent bookings of different equipment.
- Filter reservations by equipment and paginate results.
- Explore and test endpoints through interactive API documentation.

## Tech stack

Python 3.12+, FastAPI, Pydantic, SQLite, Uvicorn, pytest, and HTTPX.

## Run locally

Clone the repository, or select **Code â†’ Download ZIP** on GitHub and extract it. Open a terminal in the folder containing `requirements.txt`.

```bash
git clone https://github.com/Tanzin2005/campus-equipment-booking.git
cd campus-equipment-booking
```

### Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

These commands use the virtual environment directly; activation is unnecessary. If the `py` launcher is unavailable, use `python -m venv .venv` for the first command.

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

Open [the interactive API documentation](http://127.0.0.1:8000/docs). The database is created automatically at `data/bookings.db` and persists between restarts. Stop the server with `Ctrl+C`.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Application information |
| GET | `/equipment` | List equipment |
| POST | `/bookings` | Create a reservation |
| GET | `/bookings` | List reservations |

`GET /bookings` accepts optional `equipment_id`, `limit` (1â€“100; default 20), and `offset` (default 0) query parameters.

### Example reservation

Submit this JSON to `POST /bookings` through `/docs`. **Change the dates to a future day before submitting.** The `+05:30` offset represents Indian Standard Time; responses use UTC.

```json
{
  "equipment_id": 1,
  "student_name": "Demo Student",
  "start_at": "2026-10-01T10:00:00+05:30",
  "end_at": "2026-10-01T11:00:00+05:30"
}
```

| Status | Meaning |
| --- | --- |
| `201 Created` | Reservation saved |
| `404 Not Found` | Equipment does not exist |
| `409 Conflict` | Equipment is already reserved during the requested interval |
| `422 Unprocessable Entity` | Invalid input, such as a past start time or an end before the start |

## Preventing overlapping bookings

Two reservations overlap when:

```text
existing_start < requested_end AND existing_end > requested_start
```

The strict comparisons allow one booking to end exactly when another starts. Timestamps are normalized to UTC before storage and comparison.

The API uses a SQLite `BEGIN IMMEDIATE` transaction to acquire the write lock before checking availability and inserting a reservation. This prevents competing API requests from both reserving an available slot. Conflict prevention depends on using this write path; it is not an independent database overlap constraint.

SQLite serializes writers, and requests can exceed the lock timeout under heavy contention. This prototype has not been benchmarked for production traffic.

## Tests

On Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux / macOS:

```bash
.venv/bin/python -m pytest -q
```

The suite uses temporary databases and covers overlapping intervals, adjacent bookings, different equipment, invalid inputs, equivalent timezone offsets, persistence after restart, filtering, and four simultaneous requests for the same slot.

## Project structure

| Path | Purpose |
| --- | --- |
| `app/main.py` | API routes, request validation, and reservation logic |
| `app/database.py` | Database connections, schema, and sample equipment |
| `tests/test_bookings.py` | Automated API tests |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes local environments, caches, and database files from Git tracking |

## Planned improvements

- User registration, login, and booking ownership checks.
- Administrator-only equipment management.
- Cancellation and availability search.
- PostgreSQL migrations and database-enforced overlap prevention.
- Frontend, CI, containerization, and deployment.

## References

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html)
