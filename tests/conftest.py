import pytest

from app import create_app
from app.extensions import db
from app.models import Product, SystemConfig, User


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        db.session.add(SystemConfig(id=1))
        admin = User(name="Admin Test", email="admin@test.local", role="ADMIN")
        admin.set_password("segura-123")
        db.session.add(admin)
        db.session.add(Product(name="Agua", barcode="784000000001", category="Bebidas", price=10000, stock=20, low_stock_threshold=3))
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin(app):
    with app.app_context():
        return User.query.filter_by(email="admin@test.local").first()
