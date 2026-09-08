# Upgrade from the original starter

## Start the finished app

1. Stop your old server with Ctrl+C.
2. Extract `campus-equipment-booking-v1.zip` into a new folder.
3. Open the inner `campus-equipment-booking` folder, which contains `RUN_WINDOWS.bat`.
4. Double-click `RUN_WINDOWS.bat` and wait for server startup.
5. Open **http://127.0.0.1:8000**. You now get the application interface; `/docs` remains available.
6. Choose **Sign in → Create account**.
7. To access administration, open a terminal in this new folder and run:

```bat
.venv\Scripts\python.exe -m app.manage promote --email your-email@example.com
```

Use the email you registered, then refresh the page.

## Optional: keep your old bookings

Before starting the new app for the first time, copy the old project's `data/bookings.db` into the new project's `data` folder. Do not replace a new database that already contains accounts or reservations.

On startup, the application creates `data/bookings.pre-v1.db` as a backup and migrates the original database. Old equipment IDs, booking IDs, names, and times are preserved. Original bookings did not have verified owners, so they remain visible only to administrators and continue to block their reserved intervals. An administrator can cancel them. They are not automatically assigned to someone who registers with the same name.

Keep the original project folder until you have confirmed that the upgrade works. Do not copy `.venv` or cache folders between projects.

## API changes from the starter

- `/` now serves the frontend; `/health` reports application health.
- `/bookings` requires sign-in.
- Booking creation accepts `equipment_id`, `start_at`, `end_at`, and optional `purpose`. Remove `student_name`; it now comes from the account.
- `GET /bookings` returns an object with `items`, `total`, `limit`, and `offset` instead of a bare list.
- Authenticated writes require the session's CSRF token in `X-CSRF-Token`.
- Development dependencies are in `requirements-dev.txt`.

## Update GitHub

The supplied ZIP is a clean source package: it excludes environments, databases, secrets, and generated caches. Upload from a freshly extracted copy if using the website.

Git is the simplest way to upload all folders, including `.github/workflows`. If you use Git locally, clone the repository into a separate folder, copy the contents of this release into that clone, then run:

```bash
git status
git add .
git commit -m "Complete booking app with accounts, frontend, administration, and CI"
git push
```

Do not overwrite the clone's `.git` directory. Review `git status` before committing: it should show source files, never `.env`, `.venv`, or `data`.

With the GitHub website, upload the files and folders into the repository root. If hidden files are rejected, create them individually using **Add file → Create new file**. In particular, use the exact path `.github/workflows/tests.yml` for CI. Keep the exact filenames `README.md`, `.gitignore`, and `.dockerignore` without `.txt` suffixes.

This package does not automatically push to GitHub or deploy a server.
