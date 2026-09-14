from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


tournament_teams = db.Table(
    "tournament_teams",
    db.Column("tournament_id", db.Integer, db.ForeignKey("tournaments.id"), primary_key=True),
    db.Column("team_id", db.Integer, db.ForeignKey("teams.id"), primary_key=True),
)


ROLE_PERMISSIONS = {
    "ADMIN": {"*"},
    "OPERADOR": {
        "dashboard.view", "agenda.view", "agenda.manage", "pos.view", "pos.charge",
        "cash.manage", "products.view", "products.manage", "teams.view", "teams.manage",
        "tournaments.view", "tournaments.manage", "reports.view",
    },
    "VISOR": {"dashboard.view", "agenda.view", "teams.view", "tournaments.view", "reports.view"},
}


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="OPERADOR")
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_login = db.Column(db.DateTime)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    theme = db.Column(db.String(10), default="dark")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can(self, permission):
        permissions = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in permissions or permission in permissions


class SystemConfig(db.Model):
    __tablename__ = "system_config"
    id = db.Column(db.Integer, primary_key=True, default=1)
    facility_name = db.Column(db.String(160), nullable=False, default="Complejo PROFUT")
    court_name = db.Column(db.String(80), nullable=False, default="Cancha 1")
    description = db.Column(db.String(255), default="Cancha principal del complejo")
    timezone = db.Column(db.String(64), nullable=False, default="America/Asuncion")
    currency = db.Column(db.String(8), nullable=False, default="PYG")
    theme = db.Column(db.String(10), nullable=False, default="dark")
    reservation_price = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("100000"))
    open_time = db.Column(db.Time, nullable=False, default=time(8, 0))
    close_time = db.Column(db.Time, nullable=False, default=time(0, 0))
    slot_minutes = db.Column(db.Integer, nullable=False, default=60)
    enabled_days = db.Column(db.String(20), nullable=False, default="0,1,2,3,4,5,6")
    pix_key = db.Column(db.String(255), default="")
    pix_holder = db.Column(db.String(160), default="")
    pix_key_type = db.Column(db.String(30), default="OTRA")
    pix_qr_path = db.Column(db.String(255), default="")
    ticket_footer = db.Column(db.String(255), default="Gracias por elegir PROFUT")
    notify_reservations = db.Column(db.Boolean, default=True)
    notify_cancellations = db.Column(db.Boolean, default=True)
    notify_reminders = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class Reservation(db.Model):
    __tablename__ = "reservations"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    customer_name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), default="")
    status = db.Column(db.String(30), nullable=False, default="RESERVADA", index=True)
    reservation_type = db.Column(db.String(20), nullable=False, default="NORMAL")
    slot_lock = db.Column(db.String(40), unique=True, nullable=True)
    notes = db.Column(db.String(255), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    cancelled_at = db.Column(db.DateTime)
    account = db.relationship("Account", back_populates="reservation", uselist=False)
    creator = db.relationship("User")


class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey("reservations.id"), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="ABIERTA", index=True)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    paid_total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    reservation = db.relationship("Reservation", back_populates="account")
    items = db.relationship("AccountItem", back_populates="account", cascade="all, delete-orphan", order_by="AccountItem.id")
    payments = db.relationship("Payment", back_populates="account", order_by="Payment.created_at")


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    barcode = db.Column(db.String(64), unique=True, nullable=True, index=True)
    category = db.Column(db.String(60), nullable=False, default="General")
    price = db.Column(db.Numeric(14, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)
    image_path = db.Column(db.String(255), default="")
    color = db.Column(db.String(16), default="#087ccf")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def stock_low(self):
        return self.stock <= self.low_stock_threshold


class AccountItem(db.Model):
    __tablename__ = "account_items"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    item_type = db.Column(db.String(20), nullable=False, default="PRODUCT")
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    description = db.Column(db.String(160), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    account = db.relationship("Account", back_populates="items")
    product = db.relationship("Product")

    @property
    def pending_amount(self):
        return max(Decimal("0"), Decimal(self.subtotal) - Decimal(self.paid_amount))

    @property
    def payment_status(self):
        if Decimal(self.paid_amount) <= 0:
            return "PENDIENTE"
        if Decimal(self.paid_amount) < Decimal(self.subtotal):
            return "PARCIAL"
        return "PAGADO"


class CashSession(db.Model):
    __tablename__ = "cash_sessions"
    id = db.Column(db.Integer, primary_key=True)
    opened_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    opened_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    opening_cash = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    closed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    closed_at = db.Column(db.DateTime)
    expected_cash = db.Column(db.Numeric(14, 2), default=0)
    counted_cash = db.Column(db.Numeric(14, 2), default=0)
    difference = db.Column(db.Numeric(14, 2), default=0)
    status = db.Column(db.String(20), nullable=False, default="ABIERTA", index=True)
    opener = db.relationship("User", foreign_keys=[opened_by])
    closer = db.relationship("User", foreign_keys=[closed_by])
    payments = db.relationship("Payment", back_populates="cash_session")
    movements = db.relationship("CashMovement", back_populates="cash_session")


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(40), nullable=False, unique=True)
    idempotency_key = db.Column(db.String(64), nullable=False, unique=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    sale_id = db.Column(db.Integer, db.ForeignKey("pos_sales.id"))
    tournament_entry_id = db.Column(db.Integer, db.ForeignKey("tournament_entries.id"))
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    payer_name = db.Column(db.String(160), default="")
    reference = db.Column(db.String(120), default="")
    status = db.Column(db.String(20), nullable=False, default="CONFIRMADO")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    account = db.relationship("Account", back_populates="payments")
    sale = db.relationship("PosSale", back_populates="payment")
    tournament_entry = db.relationship("TournamentEntry", back_populates="payments")
    cash_session = db.relationship("CashSession", back_populates="payments")
    user = db.relationship("User")
    allocations = db.relationship("PaymentAllocation", back_populates="payment", cascade="all, delete-orphan")


class PaymentAllocation(db.Model):
    __tablename__ = "payment_allocations"
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    account_item_id = db.Column(db.Integer, db.ForeignKey("account_items.id"), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment = db.relationship("Payment", back_populates="allocations")
    account_item = db.relationship("AccountItem")


class PosSale(db.Model):
    __tablename__ = "pos_sales"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), nullable=False, unique=True)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="PAGADA")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    items = db.relationship("PosSaleItem", back_populates="sale", cascade="all, delete-orphan")
    payment = db.relationship("Payment", back_populates="sale", uselist=False)
    user = db.relationship("User")


class PosSaleItem(db.Model):
    __tablename__ = "pos_sale_items"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("pos_sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)
    sale = db.relationship("PosSale", back_populates="items")
    product = db.relationship("Product")


class CashMovement(db.Model):
    __tablename__ = "cash_movements"
    id = db.Column(db.Integer, primary_key=True)
    cash_session_id = db.Column(db.Integer, db.ForeignKey("cash_sessions.id"), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(30), nullable=False, default="EFECTIVO")
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(30), default="MANUAL")
    source_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    cash_session = db.relationship("CashSession", back_populates="movements")


class Team(db.Model):
    __tablename__ = "teams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    division = db.Column(db.String(80), default="Libre")
    contact_name = db.Column(db.String(120), default="")
    phone = db.Column(db.String(40), default="")
    email = db.Column(db.String(255), default="")
    emblem_path = db.Column(db.String(255), default="")
    status = db.Column(db.String(20), nullable=False, default="INCOMPLETO")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    players = db.relationship("Player", back_populates="team", cascade="all, delete-orphan")


class Player(db.Model):
    __tablename__ = "players"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    document_number = db.Column(db.String(40), default="")
    birth_date = db.Column(db.Date)
    jersey_number = db.Column(db.Integer)
    position = db.Column(db.String(60), default="")
    photo_path = db.Column(db.String(255), default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    team = db.relationship("Team", back_populates="players")


class Tournament(db.Model):
    __tablename__ = "tournaments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="BORRADOR")
    format = db.Column(db.String(80), nullable=False, default="ROUND_ROBIN")
    category = db.Column(db.String(80), default="Futbol 7 - Libre")
    registration_fee = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    group_count = db.Column(db.Integer, nullable=False, default=1)
    qualifiers_per_group = db.Column(db.Integer, nullable=False, default=2)
    draw_completed = db.Column(db.Boolean, nullable=False, default=False)
    bracket_generated = db.Column(db.Boolean, nullable=False, default=False)
    champion_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    teams = db.relationship("Team", secondary=tournament_teams, backref="tournaments")
    matches = db.relationship("Match", back_populates="tournament", cascade="all, delete-orphan")
    entries = db.relationship("TournamentEntry", back_populates="tournament", cascade="all, delete-orphan")
    groups = db.relationship("TournamentGroup", back_populates="tournament", cascade="all, delete-orphan", order_by="TournamentGroup.position")
    champion = db.relationship("Team", foreign_keys=[champion_team_id])


class TournamentGroup(db.Model):
    __tablename__ = "tournament_groups"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False, index=True)
    name = db.Column(db.String(40), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    tournament = db.relationship("Tournament", back_populates="groups")
    entries = db.relationship("TournamentEntry", back_populates="group")
    matches = db.relationship("Match", back_populates="group")
    __table_args__ = (db.UniqueConstraint("tournament_id", "name", name="uq_tournament_group_name"),)


class TournamentEntry(db.Model):
    __tablename__ = "tournament_entries"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("tournament_groups.id"))
    fee_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    paid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default="PENDIENTE")
    seed = db.Column(db.Integer)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    tournament = db.relationship("Tournament", back_populates="entries")
    team = db.relationship("Team")
    group = db.relationship("TournamentGroup", back_populates="entries")
    payments = db.relationship("Payment", back_populates="tournament_entry")
    creator = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("tournament_id", "team_id", name="uq_tournament_entry_team"),)

    @property
    def balance(self):
        return max(Decimal("0"), Decimal(self.fee_amount or 0) - Decimal(self.paid_amount or 0))


class Match(db.Model):
    __tablename__ = "matches"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    home_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    away_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    date = db.Column(db.Date)
    start_time = db.Column(db.Time)
    reservation_id = db.Column(db.Integer, db.ForeignKey("reservations.id"), unique=True)
    status = db.Column(db.String(20), nullable=False, default="PROGRAMADO")
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)
    stage = db.Column(db.String(20), nullable=False, default="GROUP")
    group_id = db.Column(db.Integer, db.ForeignKey("tournament_groups.id"))
    round_number = db.Column(db.Integer, nullable=False, default=1)
    round_name = db.Column(db.String(60), default="Fecha 1")
    matchday = db.Column(db.Integer, nullable=False, default=1)
    bracket_position = db.Column(db.Integer)
    next_match_id = db.Column(db.Integer, db.ForeignKey("matches.id"))
    next_slot = db.Column(db.String(10))
    winner_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    tournament = db.relationship("Tournament", back_populates="matches")
    home_team = db.relationship("Team", foreign_keys=[home_team_id])
    away_team = db.relationship("Team", foreign_keys=[away_team_id])
    winner_team = db.relationship("Team", foreign_keys=[winner_team_id])
    group = db.relationship("TournamentGroup", back_populates="matches")
    next_match = db.relationship("Match", remote_side=[id], foreign_keys=[next_match_id])
    reservation = db.relationship("Reservation")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, default="INFO")
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(255), default="")
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    user = db.relationship("User", backref="notifications")


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    product = db.relationship("Product")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(80), nullable=False, index=True)
    entity = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer)
    payload = db.Column(db.Text, default="{}")
    ip_address = db.Column(db.String(64), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    user = db.relationship("User")


def get_config():
    return db.session.get(SystemConfig, 1)
