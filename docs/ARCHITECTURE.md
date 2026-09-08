# Design notes

## One server, one origin

FastAPI serves both the API and the frontend. Browser requests use relative URLs, so there is no separate frontend build, CORS configuration, or second development process. The interface uses semantic HTML, native dialogs, CSS, and JavaScript. Cookies stay in the browser; session tokens are not stored in localStorage.

## Identity and authorization

Passwords use Argon2 through pwdlib. Login issues a random 256-bit session token. Only its SHA-256 digest is stored in the database. The browser receives the original in an HttpOnly, SameSite=Strict cookie. Sessions expire after 12 hours and logout deletes the current session.

A separate random CSRF token is returned to the authenticated client and required in a custom header for protected writes. Cross-origin browser writes are rejected. Server-side ownership checks apply to listing, reading, and cancelling reservations; hiding a frontend button is not an authorization boundary.

Registration cannot select an administrator role. An operator with server access creates or promotes administrators through the management command. The app does not verify email ownership or send password-reset emails.

Login is limited to 30 attempts per client IP per fixed 15-minute window; registration to 10. Counts live in the database and update atomically across workers. Configure the reverse proxy's trusted-client handling when deploying. Many users behind the same network can share an IP, so these limits may need operational tuning.

## Reservation integrity

Only `confirmed` reservations block an interval. The overlap predicate is:

```text
existing.start_at < requested.end_at AND existing.end_at > requested.start_at
```

Half-open intervals permit adjacent reservations. UTC normalization avoids comparing local clock values from different offsets.

SQLite uses `BEGIN IMMEDIATE` for writes, serializing the availability check and insert. PostgreSQL uses an equipment-row lock, then the same availability query. Its database also has an exclusion constraint over `equipment_id` and `tstzrange(start_at, end_at, '[)')`, restricted to confirmed rows. This independently prevents direct overlapping inserts. A constraint violation becomes HTTP 409.

Cancellation updates status rather than deleting history. Equipment deactivation locks the item and rejects the change if a confirmed reservation has not ended. Administrators cancel those reservations explicitly before deactivating the item.

## Migrations and legacy data

Alembic tracks the schema. The initial migration also adopts the unversioned SQLite starter, preserving IDs and normalizing timestamps. A pre-upgrade SQLite backup is created first. Legacy reservations have a null owner because a plain student name does not establish identity. They remain visible to administrators and continue blocking conflicts.

SQLite migration operations run in an explicit transaction. PostgreSQL migrations acquire an advisory transaction lock to serialize concurrent application startup. Back up operational databases before future schema upgrades.

## Boundaries

The catalog endpoint is paginated (up to 100 items per request). The frontend displays 12 equipment items per page and 10 reservations per page. Availability-only filtering happens in the database before pagination.

Docker and CI files are deployment aids, not evidence of a live deployment. There is no email delivery, notification scheduler, maintenance-period calendar, payment processing, or institutional SSO. Equipment can be taken offline through administration. See VALIDATION.md for executed checks and remaining validation limits.
