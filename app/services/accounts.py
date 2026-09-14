from decimal import Decimal

from app.extensions import db
from app.models import Account, AccountItem, Product

from .audit import log_event
from .notifications import notify_stock_low


def recalculate_account(account):
    account.total = sum((Decimal(item.subtotal or 0) for item in account.items), Decimal("0"))
    account.paid_total = sum((Decimal(item.paid_amount or 0) for item in account.items), Decimal("0"))
    account.balance = max(Decimal("0"), Decimal(account.total) - Decimal(account.paid_total))
    if account.balance == 0 and account.total > 0:
        account.status = "PAGADA"
    elif account.paid_total > 0:
        account.status = "PARCIALMENTE_PAGADA"
    else:
        account.status = "ABIERTA"
    return account


def add_product(account: Account, product: Product, qty: int, user_id: int):
    qty = int(qty)
    product = db.session.scalar(
        db.select(Product).where(Product.id == product.id).with_for_update().execution_options(populate_existing=True)
    )
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    if not product.active:
        raise ValueError("El producto está inactivo.")
    if product.stock < qty:
        raise ValueError(f"Stock insuficiente. Disponible: {product.stock}.")
    item = next(
        (
            row for row in account.items
            if row.product_id == product.id and Decimal(row.paid_amount) == 0
        ),
        None,
    )
    if item:
        item.qty += qty
        item.subtotal = Decimal(item.qty) * Decimal(item.unit_price)
    else:
        item = AccountItem(
            account=account,
            item_type="PRODUCT",
            product_id=product.id,
            description=product.name,
            qty=qty,
            unit_price=product.price,
            subtotal=Decimal(product.price) * qty,
            paid_amount=Decimal("0"),
        )
        db.session.add(item)
    previous_stock = product.stock
    product.stock -= qty
    if previous_stock > product.low_stock_threshold and product.stock <= product.low_stock_threshold:
        notify_stock_low(product)
    recalculate_account(account)
    log_event("ACCOUNT_ITEM_ADDED", "Account", account.id, {"product_id": product.id, "qty": qty}, user_id)
    db.session.commit()
    return item


def change_product_quantity(item: AccountItem, delta: int, user_id: int):
    """Change an unpaid consumption after it is in the account, restoring stock as needed."""
    delta = int(delta)
    if item.item_type != "PRODUCT" or not item.product:
        raise ValueError("Solo se puede cambiar la cantidad de un producto.")
    if Decimal(item.paid_amount) > 0:
        raise ValueError("La cantidad de un producto pagado no se puede modificar.")
    if delta not in {-1, 1}:
        raise ValueError("Cambio de cantidad inválido.")
    product = db.session.scalar(
        db.select(Product).where(Product.id == item.product_id).with_for_update().execution_options(populate_existing=True)
    )
    item.product = product
    if delta > 0 and item.product.stock < 1:
        raise ValueError("No hay más stock disponible para este producto.")

    account = item.account
    previous_qty = item.qty
    if item.qty + delta <= 0:
        return remove_unpaid_item(item, user_id)

    item.qty += delta
    item.subtotal = Decimal(item.qty) * Decimal(item.unit_price)
    item.product.stock -= delta
    recalculate_account(account)
    log_event(
        "ACCOUNT_ITEM_QUANTITY_CHANGED",
        "AccountItem",
        item.id,
        {"from": previous_qty, "to": item.qty, "delta": delta},
        user_id,
    )
    db.session.commit()
    return item


def remove_unpaid_item(item: AccountItem, user_id: int):
    if Decimal(item.paid_amount) > 0:
        raise ValueError("Un ítem pagado no se puede eliminar; requiere anulación.")
    account = item.account
    if item.product:
        item.product.stock += item.qty
    item_id = item.id
    db.session.delete(item)
    db.session.flush()
    recalculate_account(account)
    log_event("ACCOUNT_ITEM_REMOVED", "AccountItem", item_id, {"account_id": account.id}, user_id)
    db.session.commit()
