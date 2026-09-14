from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Account, AccountItem, Reservation, get_config

from .audit import log_event
from .accounts import recalculate_account
from .local_time import local_now
from .notifications import notify_users


def slot_key(day, start_time):
    return f"{day.isoformat()}:{start_time.strftime('%H:%M')}"


def slot_has_passed(day: date, start_time, now=None):
    """Return True as soon as a local reservation start time is no longer bookable."""
    now = now or local_now()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return datetime.combine(day, start_time) <= now


def generate_slots(day: date):
    config = get_config()
    if str(day.weekday()) not in config.enabled_days.split(","):
        return []
    start = datetime.combine(day, config.open_time)
    end_day = day if config.close_time > config.open_time else day + timedelta(days=1)
    end = datetime.combine(end_day, config.close_time)
    slots = []
    while start < end:
        slot_end = start + timedelta(minutes=config.slot_minutes)
        slots.append((start.time(), slot_end.time()))
        start = slot_end
    return slots


def create_reservation(day, start_time, customer_name, phone, user_id, reservation_type="NORMAL", notes="", create_account=True, commit=True):
    config = get_config()
    if slot_has_passed(day, start_time):
        raise ValueError("Ese horario ya pasó y no admite nuevas reservas.")
    valid_slots = dict(generate_slots(day))
    if start_time not in valid_slots:
        raise ValueError("El horario no pertenece a la configuración vigente.")
    lock = slot_key(day, start_time)
    if Reservation.query.filter_by(slot_lock=lock).first():
        raise ValueError("El horario acaba de ocuparse. Actualizá la agenda.")
    reservation = Reservation(
        date=day,
        start_time=start_time,
        end_time=valid_slots[start_time],
        customer_name=customer_name.strip(),
        phone=phone.strip(),
        status="RESERVADA",
        reservation_type=reservation_type,
        slot_lock=lock,
        notes=notes.strip(),
        created_by=user_id,
    )
    db.session.add(reservation)
    try:
        db.session.flush()
        if create_account:
            account = Account(reservation=reservation, status="ABIERTA")
            db.session.add(account)
            db.session.flush()
            price = Decimal(config.reservation_price)
            db.session.add(AccountItem(
                account=account,
                item_type="COURT",
                description=f"Reserva {config.court_name}",
                qty=1,
                unit_price=price,
                subtotal=price,
            ))
            db.session.flush()
            recalculate_account(account)
        log_event("RESERVATION_CREATED", "Reservation", reservation.id, {
            "date": day, "start_time": start_time, "type": reservation_type,
        }, user_id)
        if reservation_type == "NORMAL" and config.notify_reservations:
            notify_users(
                "Nueva reserva confirmada",
                f"{customer_name.strip()} reservó el {day.strftime('%d/%m/%Y')} a las {start_time.strftime('%H:%M')}.",
                f"/agenda/dia/{day.isoformat()}",
                "RESERVA",
            )
        if commit:
            db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValueError("El horario acaba de ocuparse. Actualizá la agenda.") from exc
    return reservation


def cancel_reservation(reservation, user_id, is_admin=False):
    if reservation.status != "RESERVADA":
        raise ValueError("La reserva ya no está activa.")
    if reservation.account and Decimal(reservation.account.paid_total) > 0:
        if not is_admin:
            raise PermissionError("La reserva tiene pagos y requiere autorización del administrador.")
        raise ValueError("Primero anulá o devolvé los pagos registrados desde el historial de cobros.")
    reservation.status = "CANCELADA"
    reservation.slot_lock = None
    reservation.cancelled_at = datetime.utcnow()
    if reservation.account:
        reservation.account.status = "CANCELADA"
    log_event("RESERVATION_CANCELLED", "Reservation", reservation.id, {}, user_id)
    config = get_config()
    if config.notify_cancellations:
        notify_users(
            "Reserva cancelada",
            f"Se liberó el horario {reservation.date.strftime('%d/%m/%Y')} {reservation.start_time.strftime('%H:%M')}.",
            f"/agenda/dia/{reservation.date.isoformat()}",
            "CANCELACION",
        )
    db.session.commit()


def create_block(day, start_time, notes, user_id):
    return create_reservation(
        day, start_time, "Mantenimiento", "", user_id,
        reservation_type="MANTENIMIENTO", notes=notes, create_account=False,
    )
