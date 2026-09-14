import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import CashSession, Player, Product, SystemConfig, Team, Tournament, User

from .services.reservations import create_reservation


def seed_database():
    if not db.session.get(SystemConfig, 1):
        db.session.add(SystemConfig(id=1))
    if not User.query.first():
        admin = User(name="Administrador PROFUT", email=os.getenv("ADMIN_EMAIL", "admin@profut.local").strip().lower(), role="ADMIN")
        admin.set_password(os.getenv("ADMIN_PASSWORD", "Profut2026!"))
        operator = User(name="Operador de Caja", email="operador@profut.local", role="OPERADOR")
        operator.set_password("Operador2026!")
        viewer = User(name="Visor Gerencial", email="visor@profut.local", role="VISOR")
        viewer.set_password("Visor2026!")
        db.session.add_all([admin, operator, viewer])
        db.session.flush()
    else:
        admin = User.query.filter_by(role="ADMIN").first()
    if not Product.query.first():
        db.session.add_all([
            Product(name="Agua sin gas", category="Bebidas", price=6000, stock=120, low_stock_threshold=12, color="#0ea5e9"),
            Product(name="Coca-Cola 600ml", category="Gaseosas", price=8000, stock=85, low_stock_threshold=10, color="#ef4444"),
            Product(name="Sprite 600ml", category="Gaseosas", price=8000, stock=58, low_stock_threshold=10, color="#22c55e"),
            Product(name="Powerade 500ml", category="Energéticas", price=9000, stock=32, low_stock_threshold=8, color="#0284c7"),
            Product(name="Cerveza Pilsen 355ml", category="Cervezas", price=10000, stock=42, low_stock_threshold=10, color="#eab308"),
            Product(name="Papas Lay's", category="Snacks", price=9000, stock=8, low_stock_threshold=10, color="#f59e0b"),
            Product(name="Maní salado", category="Snacks", price=6000, stock=24, low_stock_threshold=6, color="#a16207"),
            Product(name="Chocolate", category="Snacks", price=7000, stock=18, low_stock_threshold=5, color="#7c2d12"),
        ])
    db.session.flush()
    for index, product in enumerate(Product.query.filter(Product.barcode.is_(None)).order_by(Product.id), start=1):
        product.barcode = f"789000000{index:04d}"
    if not Team.query.first():
        teams = [
            Team(name="Los Halcones", division="Primera División", contact_name="Carlos Ramírez", phone="+595 981 555 123", email="halcones@profut.local", status="ACTIVO"),
            Team(name="Deportivo Sur", division="Primera División", contact_name="María Fernández", phone="+595 982 555 456", status="ACTIVO"),
            Team(name="Juventud FC", division="Segunda División", status="INCOMPLETO"),
            Team(name="Titanes", division="Primera División", status="ACTIVO"),
        ]
        db.session.add_all(teams)
        db.session.flush()
        db.session.add_all([
            Player(team=teams[0], full_name="Diego Benítez", document_number="4.521.876", jersey_number=10, position="Delantero"),
            Player(team=teams[0], full_name="Lucas Giménez", document_number="5.038.112", jersey_number=1, position="Arquero"),
        ])
        tournament = Tournament(
            name="Liga Apertura 2026", start_date=date.today(), status="BORRADOR",
            format="ROUND_ROBIN", category="Fútbol 7 - Libre", registration_fee=Decimal("150000"),
        )
        tournament.teams.extend(teams)
        db.session.add(tournament)
    db.session.commit()
    if not CashSession.query.filter_by(status="ABIERTA").first():
        db.session.add(CashSession(opened_by=admin.id, opening_cash=Decimal("100000"), status="ABIERTA"))
        db.session.commit()
    from app.models import Reservation
    if not Reservation.query.first():
        times = [datetime.strptime(value, "%H:%M").time() for value in ("18:00", "19:00", "20:00")]
        names = ["Los Halcones vs. Deportivo Sur", "Juventud FC vs. Titanes", "Entrenamiento Libre"]
        for offset, (slot, name) in enumerate(zip(times, names)):
            try:
                create_reservation(date.today() + timedelta(days=offset), slot, name, "+595 981 000 000", admin.id)
            except ValueError:
                db.session.rollback()
