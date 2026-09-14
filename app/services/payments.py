import secrets
from decimal import Decimal

from app.extensions import db
from app.models import Account, AccountItem, Payment, PaymentAllocation, utcnow

from .accounts import recalculate_account
from .audit import log_event
from .cash import get_open_session


PAYMENT_METHODS = {"EFECTIVO", "TARJETA", "TRANSFERENCIA", "PIX"}


def next_receipt_number():
    return f"PG-{utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def charge_account(account, allocations, method, user_id, payer_name="", reference="", idempotency_key=None):
    cash_session = get_open_session(for_update=True)
    if not cash_session:
        raise ValueError("La caja está cerrada. Abrí una caja antes de cobrar.")
    if method not in PAYMENT_METHODS:
        raise ValueError("Método de pago inválido.")
    account = db.session.scalar(
        db.select(Account).where(Account.id == account.id).with_for_update().execution_options(populate_existing=True)
    )
    if account.status in {"PAGADA", "CANCELADA"}:
        raise ValueError("La cuenta no admite nuevos cobros.")
    idempotency_key = idempotency_key or secrets.token_urlsafe(24)
    existing = Payment.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return existing
    normalized = []
    total = Decimal("0")
    locked_items = db.session.scalars(
        db.select(AccountItem).where(AccountItem.account_id == account.id).order_by(AccountItem.id).with_for_update().execution_options(populate_existing=True)
    ).all()
    item_map = {item.id: item for item in locked_items}
    for item_id, raw_amount in allocations.items():
        item = item_map.get(int(item_id))
        if not item:
            raise ValueError("Uno de los ítems no pertenece a esta cuenta.")
        amount = Decimal(str(raw_amount))
        if amount <= 0:
            continue
        if amount > item.pending_amount:
            raise ValueError(f"El cobro de {item.description} supera su saldo.")
        normalized.append((item, amount))
        total += amount
    if total <= 0:
        raise ValueError("Seleccioná al menos un importe pendiente.")
    payment = Payment(
        receipt_number=next_receipt_number(), idempotency_key=idempotency_key,
        account=account, cash_session=cash_session, method=method, amount=total,
        payer_name=payer_name.strip(), reference=reference.strip(), user_id=user_id,
    )
    db.session.add(payment)
    db.session.flush()
    for item, amount in normalized:
        item.paid_amount = Decimal(item.paid_amount) + amount
        db.session.add(PaymentAllocation(payment=payment, account_item=item, amount=amount))
    recalculate_account(account)
    log_event("PAYMENT_CONFIRMED", "Payment", payment.id, {
        "account_id": account.id, "method": method, "amount": total,
    }, user_id)
    db.session.commit()
    return payment


def void_payment(payment, user_id):
    if payment.status != "CONFIRMADO":
        raise ValueError("El pago ya fue anulado.")
    if payment.cash_session.status != "ABIERTA":
        raise ValueError("No se puede anular un pago de una caja ya cerrada.")
    if payment.account:
        for allocation in payment.allocations:
            item = allocation.account_item
            item.paid_amount = max(Decimal("0"), Decimal(item.paid_amount) - Decimal(allocation.amount))
        recalculate_account(payment.account)
    if payment.tournament_entry:
        entry = payment.tournament_entry
        entry.paid_amount = max(Decimal("0"), Decimal(entry.paid_amount) - Decimal(payment.amount))
        entry.payment_status = "PAGADA" if entry.balance <= 0 else "PENDIENTE"
    if payment.sale_id:
        sale = payment.sale
        if sale:
            for item in sale.items:
                item.product.stock += item.qty
            sale.status = "ANULADA"
    payment.status = "ANULADO"
    log_event("PAYMENT_VOIDED", "Payment", payment.id, {"amount": payment.amount, "method": payment.method}, user_id)
    db.session.commit()
    return payment
