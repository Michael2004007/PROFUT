import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_

from app.extensions import db
from app.models import Product, StockMovement
from app.security import permission_required
from app.services.audit import log_event

from . import bp


def save_product_image(file, required=False):
    if not file or not file.filename:
        if required:
            raise ValueError("La foto del producto es obligatoria.")
        return None
    extension = Path(file.filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("La foto debe ser PNG, JPG o WEBP.")
    upload_dir = Path(current_app.static_folder) / "uploads" / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"product-{uuid.uuid4().hex}{extension}"
    file.save(target)
    try:
        with Image.open(target) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise ValueError("El archivo no contiene una imagen válida.") from exc
    return f"uploads/products/{target.name}"


def normalize_barcode(value):
    barcode = "".join(str(value or "").strip().split())
    if len(barcode) < 4 or len(barcode) > 64:
        raise ValueError("El código de barras debe tener entre 4 y 64 caracteres.")
    return barcode


@bp.get("")
@login_required
@permission_required("products.view")
def index():
    query = Product.query
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(or_(Product.name.ilike(f"%{search}%"), Product.barcode.ilike(f"%{search}%")))
    state = request.args.get("state", "all")
    if state == "active":
        query = query.filter_by(active=True)
    elif state == "inactive":
        query = query.filter_by(active=False)
    products = query.order_by(Product.name).all()
    return render_template("products/index.html", products=products, search=search, state=state)


@bp.post("/crear")
@login_required
@permission_required("products.manage")
def create():
    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("El nombre es obligatorio.")
        barcode = normalize_barcode(request.form.get("barcode"))
        if Product.query.filter_by(barcode=barcode).first():
            raise ValueError("Ese código de barras ya pertenece a otro producto.")
        price = Decimal(request.form.get("price", "0"))
        stock = int(request.form.get("stock", 0))
        threshold = int(request.form.get("low_stock_threshold", 5))
        if price <= 0 or stock < 0 or threshold < 0:
            raise ValueError("Precio y stock deben ser valores válidos.")
        image_path = save_product_image(request.files.get("image"), required=True)
        product = Product(
            name=name, barcode=barcode, image_path=image_path,
            category=request.form.get("category", "General").strip() or "General",
            price=price, stock=stock, low_stock_threshold=threshold,
            color=request.form.get("color", "#087ccf"), active=request.form.get("active") == "on",
        )
        db.session.add(product)
        db.session.flush()
        log_event("PRODUCT_CREATED", "Product", product.id, {"name": name}, current_user.id)
        db.session.commit()
        flash("Producto creado correctamente.", "success")
    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("products.index"))


@bp.post("/<int:product_id>/editar")
@login_required
@permission_required("products.manage")
def edit(product_id):
    product = db.get_or_404(Product, product_id)
    try:
        before = {"name": product.name, "price": str(product.price), "active": product.active}
        barcode = normalize_barcode(request.form.get("barcode", product.barcode))
        duplicate = Product.query.filter(Product.barcode == barcode, Product.id != product.id).first()
        if duplicate:
            raise ValueError("Ese código de barras ya pertenece a otro producto.")
        name = request.form.get("name", product.name).strip()
        category = request.form.get("category", product.category).strip()
        price = Decimal(request.form.get("price", product.price))
        threshold = int(request.form.get("low_stock_threshold", product.low_stock_threshold))
        if not name or not category or price <= 0 or threshold < 0:
            raise ValueError("Revisá nombre, categoría, precio y stock mínimo.")
        product.name = name
        product.barcode = barcode
        product.category = category
        product.price = price
        product.low_stock_threshold = threshold
        product.active = request.form.get("active") == "on"
        image_path = save_product_image(request.files.get("image"))
        if image_path:
            product.image_path = image_path
        log_event("PRODUCT_UPDATED", "Product", product.id, {"before": before, "price": product.price, "active": product.active}, current_user.id)
        db.session.commit()
        flash("Producto actualizado.", "success")
    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("products.index"))


@bp.post("/<int:product_id>/stock")
@login_required
@permission_required("products.manage")
def adjust_stock(product_id):
    product = db.get_or_404(Product, product_id)
    try:
        quantity = int(request.form.get("quantity", 0))
        if quantity == 0 or product.stock + quantity < 0:
            raise ValueError("El ajuste dejaría un stock inválido.")
        product.stock += quantity
        movement = StockMovement(product=product, quantity=quantity, reason=request.form.get("reason", "Ajuste manual").strip(), user_id=current_user.id)
        db.session.add(movement)
        db.session.flush()
        log_event("STOCK_ADJUSTED", "Product", product.id, {"quantity": quantity, "reason": movement.reason}, current_user.id)
        db.session.commit()
        flash("Stock actualizado.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("products.index"))
