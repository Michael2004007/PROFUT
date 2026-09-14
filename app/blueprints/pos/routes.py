import secrets
from decimal import Decimal

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Account, AccountItem, CashSession, Payment, PosSale, Product
from app.security import permission_required
from app.services.accounts import add_product, change_product_quantity, remove_unpaid_item
from app.services.cash import add_movement, cash_summary, close_cash, get_open_session, open_cash
from app.services.payments import PAYMENT_METHODS, charge_account, void_payment
from app.services.pos import create_direct_sale

from . import bp


@bp.get("")
@login_required
@permission_required("pos.view")
def index():
    products = Product.query.filter_by(active=True).order_by(Product.category, Product.name).all()
    accounts = Account.query.filter(Account.status.in_(["ABIERTA", "PARCIALMENTE_PAGADA"])).join(Account.reservation).order_by(db.desc("date")).all()
    selected_account = None
    account_id = request.args.get("account", type=int)
    if account_id:
        selected_account = db.session.get(Account, account_id)
    cash = get_open_session()
    return render_template(
        "pos/index.html", products=products, accounts=accounts, account=selected_account,
        cash=cash, cash_summary=cash_summary(cash) if cash else None,
        payment_methods=sorted(PAYMENT_METHODS), idempotency_key=secrets.token_urlsafe(24),
    )


@bp.get("/caja")
@login_required
@permission_required("cash.manage")
def cash_dashboard():
    cash = get_open_session()
    closed_sessions = CashSession.query.filter_by(status="CERRADA").order_by(CashSession.closed_at.desc()).limit(10).all()
    return render_template(
        "pos/cash_dashboard.html",
        cash=cash,
        cash_summary=cash_summary(cash) if cash else None,
        closed_sessions=closed_sessions,
    )


@bp.get("/caja/abrir")
@login_required
@permission_required("cash.manage")
def open_register_form():
    if get_open_session():
        flash("La caja ya está abierta; podés gestionarla desde el panel.", "info")
        return redirect(url_for("pos.cash_dashboard"))
    return render_template("pos/cash_open.html")


@bp.get("/caja/cerrar")
@login_required
@permission_required("cash.manage")
def close_register_form():
    cash = get_open_session()
    if not cash:
        flash("No hay una caja abierta para cerrar.", "danger")
        return redirect(url_for("pos.cash_dashboard"))
    return render_template("pos/cash_close.html", cash=cash, cash_summary=cash_summary(cash))


@bp.post("/venta")
@login_required
@permission_required("pos.charge")
def direct_sale():
    data = request.get_json(silent=True) or {}
    try:
        sale = create_direct_sale(
            data.get("items", []), data.get("method", ""), current_user.id,
            data.get("reference", ""), data.get("idempotency_key"),
        )
        return jsonify({"ok": True, "sale_id": sale.id, "ticket_url": url_for("pos.sale_ticket", sale_id=sale.id)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.post("/cuenta/<int:account_id>/producto")
@login_required
@permission_required("pos.charge")
def account_add_product(account_id):
    account = db.get_or_404(Account, account_id)
    product = db.get_or_404(Product, request.form.get("product_id", type=int))
    try:
        add_product(account, product, request.form.get("qty", 1, type=int), current_user.id)
        flash(f"{product.name} agregado a la cuenta.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("pos.index", account=account.id, mode="account"))


@bp.post("/item/<int:item_id>/cantidad")
@login_required
@permission_required("pos.charge")
def change_item_quantity(item_id):
    item = db.get_or_404(AccountItem, item_id)
    account_id = item.account_id
    try:
        change_product_quantity(item, request.form.get("delta", 0, type=int), current_user.id)
        flash("Cantidad y stock actualizados.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("pos.index", account=account_id, mode="account"))


@bp.post("/cuenta/<int:account_id>/cobrar")
@login_required
@permission_required("pos.charge")
def pay_account(account_id):
    account = db.get_or_404(Account, account_id)
    allocations = {}
    pay_all = request.form.get("scope") == "all"
    for item in account.items:
        if pay_all or request.form.get(f"item_{item.id}") == "on":
            raw = request.form.get(f"amount_{item.id}", str(item.pending_amount))
            allocations[item.id] = raw
    try:
        payment = charge_account(
            account, allocations, request.form.get("method", ""), current_user.id,
            request.form.get("payer_name", ""), request.form.get("reference", ""),
            request.form.get("idempotency_key"),
        )
        flash(f"Cobro {payment.receipt_number} confirmado por {payment.amount:,.0f}.", "success")
        return redirect(url_for("pos.ticket", payment_id=payment.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("pos.index", account=account.id, mode="account"))


@bp.post("/item/<int:item_id>/eliminar")
@login_required
@permission_required("pos.charge")
def remove_item(item_id):
    item = db.get_or_404(AccountItem, item_id)
    account_id = item.account_id
    try:
        remove_unpaid_item(item, current_user.id)
        flash("Ítem eliminado y stock repuesto.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pos.index", account=account_id, mode="account"))


@bp.post("/caja/abrir")
@login_required
@permission_required("cash.manage")
def open_register():
    try:
        open_cash(current_user.id, request.form.get("opening_cash", "0"))
        flash("Caja abierta correctamente.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pos.cash_dashboard"))


@bp.post("/caja/movimiento")
@login_required
@permission_required("cash.manage")
def movement():
    cash = get_open_session()
    try:
        if not cash:
            raise ValueError("No hay una caja abierta.")
        add_movement(cash, request.form.get("movement_type", ""), request.form.get("amount", "0"), request.form.get("description", ""), current_user.id)
        flash("Movimiento de caja registrado.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pos.cash_dashboard"))


@bp.post("/caja/cerrar")
@login_required
@permission_required("cash.manage")
def close_register():
    cash = get_open_session()
    try:
        if not cash:
            raise ValueError("No hay una caja abierta.")
        session = close_cash(cash, request.form.get("counted_cash", "0"), current_user.id)
        flash(f"Caja cerrada. Diferencia: {session.difference:,.0f}.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pos.cash_dashboard"))


@bp.get("/ticket/pago/<int:payment_id>")
@login_required
@permission_required("pos.view")
def ticket(payment_id):
    payment = db.get_or_404(Payment, payment_id)
    return render_template("tickets/receipt.html", payment=payment, sale=None)


@bp.get("/ticket/venta/<int:sale_id>")
@login_required
@permission_required("pos.view")
def sale_ticket(sale_id):
    sale = db.get_or_404(PosSale, sale_id)
    return render_template("tickets/receipt.html", payment=sale.payment, sale=sale)


@bp.post("/pago/<int:payment_id>/anular")
@login_required
@permission_required("users.manage")
def void(payment_id):
    payment = db.get_or_404(Payment, payment_id)
    try:
        void_payment(payment, current_user.id)
        flash("Pago anulado y saldos recalculados.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pos.ticket", payment_id=payment.id))
