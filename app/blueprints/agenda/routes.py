import calendar
from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Reservation
from app.security import permission_required
from app.services.local_time import local_today
from app.services.reservations import cancel_reservation, create_block, create_reservation, generate_slots, slot_has_passed

from . import bp


MONTHS_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


@bp.get("")
@login_required
@permission_required("agenda.view")
def months():
    today = local_today()
    year = request.args.get("year", today.year, type=int)
    if year < today.year - 5 or year > today.year + 2:
        year = today.year
    counts = dict(db.session.query(db.extract("month", Reservation.date), db.func.count(Reservation.id)).filter(
        db.extract("year", Reservation.date) == year, Reservation.status == "RESERVADA"
    ).group_by(db.extract("month", Reservation.date)).all())
    return render_template("agenda/months.html", year=year, months=MONTHS_ES, counts=counts)


@bp.get("/<int:year>/<int:month>")
@login_required
@permission_required("agenda.view")
def days(year, month):
    if month not in range(1, 13):
        abort(404)
    _, last_day = calendar.monthrange(year, month)
    month_days = []
    today = local_today()
    for number in range(1, last_day + 1):
        day = date(year, month, number)
        reservations = Reservation.query.filter_by(date=day, status="RESERVADA").count()
        total = len(generate_slots(day))
        if day < today:
            status = "past"
        elif reservations == 0:
            status = "available"
        elif reservations < total:
            status = "partial"
        else:
            status = "full"
        month_days.append({"date": day, "weekday": DAYS_ES[day.weekday()], "reserved": reservations, "total": total, "status": status})
    return render_template("agenda/days.html", year=year, month=month, month_name=MONTHS_ES[month - 1], days=month_days)


@bp.get("/dia/<date_value>")
@login_required
@permission_required("agenda.view")
def slots(date_value):
    try:
        day = date.fromisoformat(date_value)
    except ValueError:
        abort(404)
    reservations = {row.start_time: row for row in Reservation.query.filter_by(date=day, status="RESERVADA").all()}
    slot_rows = [
        {
            "start": start,
            "end": end,
            "reservation": reservations.get(start),
            "is_past": slot_has_passed(day, start),
        }
        for start, end in generate_slots(day)
    ]
    return render_template("agenda/slots.html", day=day, slots=slot_rows, month_name=MONTHS_ES[day.month - 1])


@bp.post("/reservar")
@login_required
@permission_required("agenda.manage")
def reserve():
    try:
        day = date.fromisoformat(request.form["date"])
        start = datetime.strptime(request.form["start_time"], "%H:%M").time()
        create_reservation(day, start, request.form.get("customer_name", ""), request.form.get("phone", ""), current_user.id, notes=request.form.get("notes", ""))
        flash("Reserva creada y cuenta abierta automáticamente.", "success")
    except (ValueError, KeyError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("agenda.slots", date_value=request.form.get("date", local_today().isoformat())))


@bp.post("/bloquear")
@login_required
@permission_required("users.manage")
def block():
    try:
        day = date.fromisoformat(request.form["date"])
        start = datetime.strptime(request.form["start_time"], "%H:%M").time()
        create_block(day, start, request.form.get("notes", "Mantenimiento"), current_user.id)
        flash("Horario bloqueado por mantenimiento.", "success")
    except (ValueError, KeyError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("agenda.slots", date_value=request.form.get("date", local_today().isoformat())))


@bp.post("/reserva/<int:reservation_id>/cancelar")
@login_required
@permission_required("agenda.manage")
def cancel(reservation_id):
    reservation = db.get_or_404(Reservation, reservation_id)
    try:
        cancel_reservation(reservation, current_user.id, current_user.role == "ADMIN")
        flash("Reserva cancelada. El horario volvió a estar disponible.", "success")
    except (ValueError, PermissionError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("agenda.slots", date_value=reservation.date.isoformat()))
