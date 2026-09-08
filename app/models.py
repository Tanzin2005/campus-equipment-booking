"""SQLAlchemy Core tables; schema changes are versioned in migrations/."""
import sqlalchemy as sa

metadata = sa.MetaData()
users = sa.Table("users", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(80), nullable=False),
    sa.Column("email", sa.String(254), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(512), nullable=False),
    sa.Column("role", sa.String(16), nullable=False, server_default="student"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sessions = sa.Table("sessions", metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("csrf_token", sa.String(64), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
)
equipment = sa.Table("equipment", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(100), nullable=False),
    sa.Column("location", sa.String(100), nullable=False),
    sa.Column("category", sa.String(40), nullable=False, server_default="Electronics"),
    sa.Column("description", sa.String(600), nullable=False, server_default=""),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
)
bookings = sa.Table("bookings", metadata,
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
    sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_booking_status"),
)
auth_attempts = sa.Table("auth_attempts", metadata,
    sa.Column("key", sa.String(100), primary_key=True),
    sa.Column("count", sa.Integer, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
)
