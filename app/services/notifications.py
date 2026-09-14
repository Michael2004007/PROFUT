from app.extensions import db
from app.models import Notification, User


def notify_users(title, message, link="", category="INFO", roles=("ADMIN", "OPERADOR")):
    users = User.query.filter(User.active.is_(True), User.role.in_(roles)).all()
    notifications = [
        Notification(user_id=user.id, title=title, message=message, link=link, category=category)
        for user in users
    ]
    db.session.add_all(notifications)
    return notifications


def notify_stock_low(product):
    existing = Notification.query.filter(
        Notification.is_read.is_(False),
        Notification.title == f"Stock bajo: {product.name}",
    ).first()
    if not existing:
        notify_users(
            f"Stock bajo: {product.name}",
            f"Quedan {product.stock} unidades; el mínimo configurado es {product.low_stock_threshold}.",
            f"/productos?q={product.name}",
            "STOCK",
        )

