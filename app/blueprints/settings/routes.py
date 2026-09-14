import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from PIL import Image, UnidentifiedImageError

from app.extensions import db
from app.models import get_config
from app.security import permission_required
from app.services.audit import log_event

from . import bp


@bp.get("")
@login_required
@permission_required("users.manage")
def index():
    return render_template("settings/index.html", config=get_config())


@bp.post("")
@login_required
@permission_required("users.manage")
def update():
    config = get_config()
    before = {"reservation_price": str(config.reservation_price), "open_time": str(config.open_time), "close_time": str(config.close_time)}
    try:
        config.facility_name = request.form.get("facility_name", config.facility_name).strip()
        config.court_name = request.form.get("court_name", config.court_name).strip()
        config.description = request.form.get("description", config.description).strip()
        config.timezone = request.form.get("timezone", config.timezone).strip()
        config.currency = request.form.get("currency", config.currency).strip().upper()
        config.theme = request.form.get("theme", config.theme)
        if config.theme not in {"dark", "light"}:
            raise ValueError("Tema inválido.")
        current_user.theme = config.theme
        config.reservation_price = Decimal(request.form.get("reservation_price", config.reservation_price))
        config.open_time = datetime.strptime(request.form.get("open_time", "08:00"), "%H:%M").time()
        config.close_time = datetime.strptime(request.form.get("close_time", "00:00"), "%H:%M").time()
        config.slot_minutes = int(request.form.get("slot_minutes", 60))
        enabled_days = request.form.getlist("enabled_days")
        if not enabled_days:
            raise ValueError("Habilitá al menos un día de operación.")
        config.enabled_days = ",".join(enabled_days)
        if config.slot_minutes not in {30, 45, 60, 90, 120} or config.reservation_price <= 0:
            raise ValueError("Precio o intervalo de reserva inválido.")
        config.pix_key = request.form.get("pix_key", "").strip()
        config.pix_holder = request.form.get("pix_holder", "").strip()
        config.pix_key_type = request.form.get("pix_key_type", "OTRA")
        config.ticket_footer = request.form.get("ticket_footer", "").strip()
        config.notify_reservations = request.form.get("notify_reservations") == "on"
        config.notify_cancellations = request.form.get("notify_cancellations") == "on"
        config.notify_reminders = request.form.get("notify_reminders") == "on"
        qr_file = request.files.get("pix_qr")
        if qr_file and qr_file.filename:
            upload_dir = Path(current_app.static_folder) / "uploads" / "pix"
            upload_dir.mkdir(parents=True, exist_ok=True)
            extension = Path(qr_file.filename).suffix.lower()
            if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise ValueError("El QR debe ser PNG, JPG o WEBP.")
            target = upload_dir / f"pix-{uuid.uuid4().hex}{extension}"
            qr_file.save(target)
            try:
                with Image.open(target) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError) as exc:
                target.unlink(missing_ok=True)
                raise ValueError("El archivo no contiene una imagen válida.") from exc
            config.pix_qr_path = f"uploads/pix/{target.name}"
        log_event("SETTINGS_UPDATED", "SystemConfig", config.id, {"before": before, "price": config.reservation_price}, current_user.id)
        db.session.commit()
        flash("Configuración guardada.", "success")
    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("settings.index"))


@bp.post("/tema")
@login_required
def update_theme():
    data = request.get_json(silent=True) or {}
    theme = data.get("theme")
    if theme not in {"dark", "light"}:
        return jsonify({"ok": False, "error": "Tema inválido"}), 400
    current_user.theme = theme
    db.session.commit()
    return jsonify({"ok": True, "theme": theme})
