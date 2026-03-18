"""Initial schema — all tables and indexes (customers, vehicles, dealerships,
service_types, technicians, service_bays, appointments).

Includes:
  - BigInteger auto-increment PKs (no UUIDs)
  - vehicle_number (BigInt surrogate ref for VIN-less vehicles)
  - customer address fields (address_line1/2, city, state, postal_code, country)
  - email is indexed but NOT unique (duplicates allowed)

Revision ID: 001
Revises:
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── customers ──────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id",            sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("first_name",    sa.String(100), nullable=False),
        sa.Column("last_name",     sa.String(100), nullable=False),
        sa.Column("email",         sa.String(255), nullable=False),
        sa.Column("phone",         sa.String(30),  nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city",          sa.String(100), nullable=True),
        sa.Column("state",         sa.String(100), nullable=True),
        sa.Column("postal_code",   sa.String(20),  nullable=True),
        sa.Column("country",       sa.String(100), nullable=True, server_default="US"),
        sa.Column("created_at",    sa.DateTime,    nullable=False),
    )
    op.create_index("idx_customers_email", "customers", ["email"])
    op.create_index("idx_customers_phone", "customers", ["phone"])

    # ── dealerships ────────────────────────────────────────────────────────────
    op.create_table(
        "dealerships",
        sa.Column("id",       sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name",     sa.String(255), nullable=False),
        sa.Column("address",  sa.String(500), nullable=True),
        sa.Column("city",     sa.String(100), nullable=False),
        sa.Column("state",    sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64),  nullable=False, server_default="UTC"),
    )
    op.create_index("idx_dealerships_name", "dealerships", ["name"])

    # ── service_types ──────────────────────────────────────────────────────────
    op.create_table(
        "service_types",
        sa.Column("id",                sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name",              sa.String(255), nullable=False),
        sa.Column("description",       sa.Text,        nullable=True),
        sa.Column("duration_minutes",  sa.Integer,     nullable=False),
        sa.Column("required_bay_type", sa.String(50),  nullable=False),
    )

    # ── vehicles ───────────────────────────────────────────────────────────────
    op.create_table(
        "vehicles",
        sa.Column("id",             sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("customer_id",    sa.BigInteger, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("vehicle_number", sa.BigInteger, nullable=True),
        sa.Column("vin",            sa.String(17), nullable=True, unique=True),
        sa.Column("make",           sa.String(100), nullable=False),
        sa.Column("model",          sa.String(100), nullable=False),
        sa.Column("year",           sa.Integer,     nullable=False),
        sa.Column("created_at",     sa.DateTime,    nullable=False),
    )
    op.create_index("idx_vehicles_customer_id", "vehicles", ["customer_id"])
    op.create_index(
        "ix_vehicles_vehicle_number", "vehicles", ["vehicle_number"], unique=True
    )

    # ── technicians ────────────────────────────────────────────────────────────
    op.create_table(
        "technicians",
        sa.Column("id",              sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dealership_id",   sa.BigInteger, sa.ForeignKey("dealerships.id"), nullable=False),
        sa.Column("first_name",      sa.String(100), nullable=False),
        sa.Column("last_name",       sa.String(100), nullable=False),
        sa.Column("employee_number", sa.String(50),  nullable=False, unique=True),
        sa.Column("is_active",       sa.Boolean,     nullable=False, server_default=sa.true()),
    )
    # Partial index on active technicians (PostgreSQL only)
    op.execute(
        """
        CREATE INDEX idx_technicians_dealership_active
            ON technicians (dealership_id)
            WHERE is_active = TRUE
        """
    )

    # ── technician_qualifications ─────────────────────────────────────────────
    op.create_table(
        "technician_qualifications",
        sa.Column("technician_id",   sa.BigInteger, sa.ForeignKey("technicians.id"),   primary_key=True),
        sa.Column("service_type_id", sa.BigInteger, sa.ForeignKey("service_types.id"), primary_key=True),
        sa.Column("certified_at",    sa.DateTime,   nullable=False),
    )
    op.create_index(
        "idx_tech_qual_service_type",
        "technician_qualifications",
        ["service_type_id", "technician_id"],
    )

    # ── service_bays ───────────────────────────────────────────────────────────
    op.create_table(
        "service_bays",
        sa.Column("id",            sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dealership_id", sa.BigInteger, sa.ForeignKey("dealerships.id"), nullable=False),
        sa.Column("bay_number",    sa.String(20), nullable=False),
        sa.Column("bay_type",      sa.String(50), nullable=False),
        sa.Column("is_active",     sa.Boolean,    nullable=False, server_default=sa.true()),
    )
    op.execute(
        """
        CREATE INDEX idx_bays_dealership_type
            ON service_bays (dealership_id, bay_type)
            WHERE is_active = TRUE
        """
    )

    # ── appointments ───────────────────────────────────────────────────────────
    op.create_table(
        "appointments",
        sa.Column("id",                    sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("customer_id",           sa.BigInteger, sa.ForeignKey("customers.id"),    nullable=False),
        sa.Column("booked_by_customer_id", sa.BigInteger, sa.ForeignKey("customers.id"),    nullable=True),
        sa.Column("vehicle_id",            sa.BigInteger, sa.ForeignKey("vehicles.id"),     nullable=False),
        sa.Column("dealership_id",         sa.BigInteger, sa.ForeignKey("dealerships.id"),  nullable=False),
        sa.Column("service_type_id",       sa.BigInteger, sa.ForeignKey("service_types.id"), nullable=False),
        sa.Column("technician_id",         sa.BigInteger, sa.ForeignKey("technicians.id"),  nullable=False),
        sa.Column("service_bay_id",        sa.BigInteger, sa.ForeignKey("service_bays.id"), nullable=False),
        sa.Column("scheduled_start",       sa.DateTime,   nullable=False),
        sa.Column("scheduled_end",         sa.DateTime,   nullable=False),
        sa.Column("status",                sa.String(20), nullable=False),
        sa.Column("notes",                 sa.Text,       nullable=True),
        sa.Column("created_at",            sa.DateTime,   nullable=False),
        sa.Column("updated_at",            sa.DateTime,   nullable=False),
    )
    # Partial indexes on CONFIRMED rows for overlap detection
    op.execute(
        """
        CREATE INDEX idx_appointments_technician_time
            ON appointments (technician_id, scheduled_start, scheduled_end)
            WHERE status = 'CONFIRMED'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_appointments_bay_time
            ON appointments (service_bay_id, scheduled_start, scheduled_end)
            WHERE status = 'CONFIRMED'
        """
    )
    op.create_index(
        "idx_appointments_dealership_status",
        "appointments",
        ["dealership_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("service_bays")
    op.drop_table("technician_qualifications")
    op.drop_table("technicians")
    op.drop_table("vehicles")
    op.drop_table("service_types")
    op.drop_table("dealerships")
    op.drop_table("customers")
