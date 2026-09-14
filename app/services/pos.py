import secrets
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Payment, PosSale, PosSaleItem, Product, utcnow

from .audit import log_event
from .cash import get_open_session
from .payments import PAYMENT_METHODS, next_receipt_number
from .notifications import notify_stock_low


def create_direct_sale(lines, method, user_id, reference="", idempotency_key=None):
    cash_session = get_open_session(for_update=True)
    if not cash_session:
        raise ValueError("La caja está cerrada. Abrí una caja antes de cobrar.")
    if method not in PAYMENT_METHODS:
        raise ValueError("Método de pago inválido.")
    idempotency_key = idempotency_key or secrets.token_urlsafe(24)
    existing = Payment.query.filter_by(idempotency_key=idempotency_key).first()
    if existing and existing.sale_id:
        return existing.sale
    requested = defaultdict(int)
    try:
        for raw in lines:
            requested[int(raw["product_id"])] += int(raw["qty"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("El carrito contiene un producto o cantidad inválida.") from exc
    if any(qty <= 0 for qty in requested.values()):
        raise ValueError("Las cantidades del carrito deben ser mayores a cero.")
    product_rows = db.session.scalars(
        db.select(Product).where(Product.id.in_(sorted(requested))).order_by(Product.id).with_for_update()
    ).all() if requested else []
    products = {product.id: product for product in product_rows}
    if len(products) != len(requested):
        raise ValueError("Uno de los productos ya no está disponible.")
    normalized = []
    total = Decimal("0")
    for product_id, qty in requested.items():
        product = products[product_id]
        if not product or not product.active:
            raise ValueError("Uno de los productos ya no está disponible.")
        if qty <= 0 or product.stock < qty:
            raise ValueError(f"Stock insuficiente para {product.name}.")
        subtotal = Decimal(product.price) * qty
        normalized.append((product, qty, subtotal))
        total += subtotal
    if not normalized:
        raise ValueError("El carrito está vacío.")
    sale = PosSale(
        number=f"V-{utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}",
        total=total, user_id=user_id, cash_session_id=cash_session.id,
    )
    db.session.add(sale)
    db.session.flush()
    for product, qty, subtotal in normalized:
        previous_stock = product.stock
        product.stock -= qty
        if previous_stock > product.low_stock_threshold and product.stock <= product.low_stock_threshold:
            notify_stock_low(product)
        db.session.add(PosSaleItem(sale=sale, product=product, qty=qty, unit_price=product.price, subtotal=subtotal))
    payment = Payment(
        receipt_number=next_receipt_number(), idempotency_key=idempotency_key,
        sale_id=sale.id, cash_session_id=cash_session.id, method=method,
        amount=total, reference=reference.strip(), user_id=user_id,
    )
    db.session.add(payment)
    db.session.flush()
    log_event("POS_SALE_CONFIRMED", "PosSale", sale.id, {"number": sale.number, "amount": total}, user_id)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        existing = Payment.query.filter_by(idempotency_key=idempotency_key).first()
        if existing and existing.sale_id:
            return existing.sale
        raise ValueError("La venta ya fue procesada o cambió mientras se confirmaba.") from exc
    return sale
