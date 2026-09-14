import secrets
import string

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import AuditLog, User
from app.security import permission_required
from app.services.audit import log_event

from . import bp


def temporary_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@bp.get("")
@login_required
@permission_required("users.manage")
def index():
    users = User.query.order_by(User.name).all()
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template("users/index.html", users=users, logs=logs)


@bp.post("/crear")
@login_required
@permission_required("users.manage")
def create():
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "OPERADOR")
    password = request.form.get("password", "") or temporary_password()
    if not name or "@" not in email or role not in {"ADMIN", "OPERADOR", "VISOR"} or len(password) < 8:
        flash("Revisá nombre, correo, rol y contraseña (mínimo 8 caracteres).", "danger")
        return redirect(url_for("users.index"))
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.flush()
        log_event("USER_CREATED", "User", user.id, {"email": email, "role": role}, current_user.id)
        db.session.commit()
        flash(f"Usuario creado. Contraseña inicial: {password}", "success")
    except Exception:
        db.session.rollback()
        flash("Ya existe un usuario con ese correo.", "danger")
    return redirect(url_for("users.index"))


@bp.post("/<int:user_id>/editar")
@login_required
@permission_required("users.manage")
def edit(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role", user.role)
    if role not in {"ADMIN", "OPERADOR", "VISOR"}:
        flash("Rol inválido.", "danger")
        return redirect(url_for("users.index"))
    if user.id == current_user.id and request.form.get("active") != "on":
        flash("No podés inactivar tu propia cuenta.", "danger")
        return redirect(url_for("users.index"))
    before = {"name": user.name, "role": user.role, "active": user.active}
    user.name = request.form.get("name", user.name).strip()
    user.role = role
    user.active = request.form.get("active") == "on"
    log_event("USER_UPDATED", "User", user.id, {"before": before, "role": role, "active": user.active}, current_user.id)
    db.session.commit()
    flash("Usuario actualizado.", "success")
    return redirect(url_for("users.index"))


@bp.post("/<int:user_id>/restablecer")
@login_required
@permission_required("users.manage")
def reset_password(user_id):
    user = db.get_or_404(User, user_id)
    password = temporary_password()
    user.set_password(password)
    user.failed_login_attempts = 0
    user.locked_until = None
    log_event("PASSWORD_RESET", "User", user.id, {}, current_user.id)
    db.session.commit()
    flash(f"Nueva contraseña temporal para {user.name}: {password}", "success")
    return redirect(url_for("users.index"))

