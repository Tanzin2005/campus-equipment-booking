# Release validation — 8 September 2026

## Executed

- SQLite/API suite: **32 passed, 1 skipped** using Python 3.12.
- The skipped test is PostgreSQL's database exclusion constraint, which requires a running PostgreSQL server.
- Tests cover account registration and sign-in, Argon2 storage, secure-cookie configuration, session expiry/revocation, CSRF and origin checks, ownership, administrator permissions, booking conflicts, adjacent intervals, four simultaneous requests, cancellation, offline equipment, search, pagination, availability privacy, migrations, and persistence.
- The original SQLite schema was upgraded in a test; equipment and booking IDs, names, and times were preserved, and a pre-upgrade backup was created.
- Frontend HTML, CSS, JavaScript, health endpoint, and OpenAPI schema were served successfully through the test client.
- JavaScript syntax passed `node --check app/static/app.js`.

## Not executed in this environment

- PostgreSQL runtime tests: the environment could not start an unprivileged PostgreSQL process. The PostgreSQL implementation and exclusion-constraint migration are included, along with a GitHub Actions service job that tests them.
- Docker build/start: Docker is unavailable in the build environment.
- Interactive browser, visual, and cross-browser testing. Responsive styles and native dialogs are implemented, but their rendered appearance and complete browser interactions were not inspected here.
- GitHub Actions runs and hosted deployment. The remote GitHub repository is unchanged until the release files are uploaded or pushed.

One upstream Starlette/AnyIO deprecation warning remains (`BlockingPortal` import location). It does not fail the passing tests and is not suppressed by this project. The earlier HTTPX deprecation is avoided by using HTTPX2 for the test client.

No production traffic, user-count, performance, or deployment claims are made.
