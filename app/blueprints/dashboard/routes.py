from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models import Account, Notification, Payment, Product, Reservation, Tournament
from app.security import permission_required
from app.services.cash import cash_summary, get_open_session
from app.services.local_time import local_today, utc_bounds_for_local_dates
from app.services.reservations import generate_slots, slot_has_passed

from . import bp


@bp.get("/")
@login_required
@permission_required("dashboard.view")
def index():
    today = local_today()
    day_start, day_end = utc_bounds_for_local_dates(today, today)
    reservations = Reservation.query.filter_by(date=today, status="RESERVADA").order_by(Reservation.start_time).all()
    upcoming_reservations = [row for row in reservations if not slot_has_passed(today, row.start_time)]
    income = db.session.scalar(db.select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == "CONFIRMADO", Payment.created_at.between(day_start, day_end)
    )) or Decimal("0")
    pending = db.session.scalar(db.select(func.coalesce(func.sum(Account.balance), 0)).where(
        Account.status.in_(["ABIERTA", "PARCIALMENTE_PAGADA"])
    )) or Decimal("0")
    occupied_times = {row.start_time for row in reservations}
    available = sum(1 for start, _end in generate_slots(today) if start not in occupied_times and not slot_has_passed(today, start))
    cash = get_open_session()
    summary = cash_summary(cash) if cash else None
    payments = Payment.query.filter(Payment.created_at.between(day_start, day_end), Payment.status == "CONFIRMADO").all()
    methods = {method: sum((Decimal(p.amount) for p in payments if p.method == method), Decimal("0")) for method in ("EFECTIVO", "TARJETA", "TRANSFERENCIA", "PIX")}
    low_stock = Product.query.filter(Product.active.is_(True), Product.stock <= Product.low_stock_threshold).all()
    tournaments = Tournament.query.filter(Tournament.status.in_(["PROGRAMADO", "EN_CURSO"])).order_by(Tournament.start_date).limit(4).all()
    return render_template(
        "dashboard/index.html", reservations=reservations, upcoming_reservations=upcoming_reservations, income=income, pending=pending,
        available=available, cash=cash, cash_summary=summary, methods=methods,
        low_stock=low_stock, tournaments=tournaments,
    )


@bp.get("/notificaciones")
@login_required
def notifications():
    rows = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return render_template("dashboard/notifications.html", notifications=rows)


@bp.post("/notificaciones/<int:notification_id>/leer")
@login_required
def read_notification(notification_id):
    notification = db.get_or_404(Notification, notification_id)
    if notification.user_id != current_user.id:
        return redirect(url_for("dashboard.notifications"))
    notification.is_read = True
    db.session.commit()
    return redirect(notification.link or request.referrer or url_for("dashboard.notifications"))


@bp.post("/notificaciones/leer-todas")
@login_required
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    flash("Notificaciones marcadas como leídas.", "success")
    return redirect(request.referrer or url_for("dashboard.notifications"))
