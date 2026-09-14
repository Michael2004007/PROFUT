from decimal import Decimal

from app.extensions import db
from app.models import CashMovement, CashSession, Payment, SystemConfig, utcnow

from .audit import log_event


def get_open_session(for_update=False):
    statement = db.select(CashSession).where(CashSession.status == "ABIERTA").order_by(CashSession.opened_at.desc())
    if for_update:
        statement = statement.with_for_update()
    return db.session.scalar(statement)


def open_cash(user_id, opening_cash):
    # Serializes the "no open cash" check across production workers.
    db.session.execute(db.select(SystemConfig).where(SystemConfig.id == 1).with_for_update())
    if get_open_session():
        raise ValueError("Ya existe una caja abierta.")
    amount = Decimal(str(opening_cash or 0))
    if amount < 0:
        raise ValueError("El fondo inicial no puede ser negativo.")
    session = CashSession(opened_by=user_id, opening_cash=amount, status="ABIERTA")
    db.session.add(session)
    db.session.flush()
    log_event("CASH_OPENED", "CashSession", session.id, {"opening_cash": amount}, user_id)
    db.session.commit()
    return session


def cash_summary(session):
    confirmed = [p for p in session.payments if p.status == "CONFIRMADO"]
    by_method = {method: Decimal("0") for method in ("EFECTIVO", "TARJETA", "TRANSFERENCIA", "PIX")}
    for payment in confirmed:
        by_method[payment.method] = by_method.get(payment.method, Decimal("0")) + Decimal(payment.amount)
    manual_in = sum((Decimal(m.amount) for m in session.movements if m.movement_type == "IN" and m.method == "EFECTIVO"), Decimal("0"))
    manual_out = sum((Decimal(m.amount) for m in session.movements if m.movement_type == "OUT" and m.method == "EFECTIVO"), Decimal("0"))
    expected = Decimal(session.opening_cash) + by_method["EFECTIVO"] + manual_in - manual_out
    return {"by_method": by_method, "total": sum(by_method.values()), "manual_in": manual_in, "manual_out": manual_out, "expected": expected}


def add_movement(session, movement_type, amount, description, user_id):
    session = db.session.scalar(
        db.select(CashSession).where(CashSession.id == session.id).with_for_update().execution_options(populate_existing=True)
    )
    if session.status != "ABIERTA":
        raise ValueError("La caja está cerrada.")
    amount = Decimal(str(amount))
    if amount <= 0 or movement_type not in {"IN", "OUT"}:
        raise ValueError("Movimiento inválido.")
    movement = CashMovement(cash_session=session, movement_type=movement_type, amount=amount, description=description.strip())
    db.session.add(movement)
    db.session.flush()
    log_event("CASH_MOVEMENT", "CashMovement", movement.id, {"type": movement_type, "amount": amount}, user_id)
    db.session.commit()
    return movement


def close_cash(session, counted_cash, user_id):
    session = db.session.scalar(
        db.select(CashSession).where(CashSession.id == session.id).with_for_update().execution_options(populate_existing=True)
    )
    if session.status != "ABIERTA":
        raise ValueError("La caja ya está cerrada.")
    summary = cash_summary(session)
    counted = Decimal(str(counted_cash))
    session.expected_cash = summary["expected"]
    session.counted_cash = counted
    session.difference = counted - summary["expected"]
    session.closed_by = user_id
    session.closed_at = utcnow()
    session.status = "CERRADA"
    log_event("CASH_CLOSED", "CashSession", session.id, {
        "expected": session.expected_cash, "counted": counted, "difference": session.difference,
    }, user_id)
    db.session.commit()
    return session
