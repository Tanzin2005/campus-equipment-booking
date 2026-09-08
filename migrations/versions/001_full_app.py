"""Complete schema; adopt the original unversioned SQLite starter safely."""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "001_full_app"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    inspector = sa.inspect(db)
    existing = set(inspector.get_table_names())
    legacy = "bookings" in existing and "user_id" not in {c["name"] for c in inspector.get_columns("bookings")}
    old_bookings = list(db.exec_driver_sql("SELECT * FROM bookings").mappings()) if legacy else []
    if legacy:
        op.drop_table("bookings")
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="student"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('student', 'admin')", name="ck_user_role"))
    op.create_table("sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    if "equipment" not in existing:
        op.create_table("equipment", sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("location", sa.String(100), nullable=False))
    op.add_column("equipment", sa.Column("category", sa.String(40), nullable=False, server_default="Electronics"))
    op.add_column("equipment", sa.Column("description", sa.String(600), nullable=False, server_default=""))
    op.add_column("equipment", sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()))
    table = op.create_table("bookings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("student_name", sa.String(80), nullable=False),
        sa.Column("purpose", sa.String(240), nullable=False, server_default=""),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_at < end_at", name="ck_booking_interval"),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_booking_status"))
    op.create_index("ix_booking_equipment_time", "bookings", ["equipment_id", "status", "start_at", "end_at"])
    op.create_index("ix_booking_owner_time", "bookings", ["user_id", "start_at"])
    for row in old_bookings:
        values = dict(row)
        for key in ("start_at", "end_at"):
            parsed = datetime.fromisoformat(values[key])
            values[key] = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        values.update(user_id=None, purpose="Imported from the original prototype", status="confirmed", created_at=datetime.now(timezone.utc))
        db.execute(table.insert().values(**values))
    op.create_table("auth_attempts", sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_attempts_expires_at", "auth_attempts", ["expires_at"])
    if db.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute("ALTER TABLE bookings ADD CONSTRAINT no_overlapping_bookings EXCLUDE USING gist "
                   "(equipment_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE (status = 'confirmed')")


def downgrade():
    raise RuntimeError("Restore a database backup to downgrade this migration.")
