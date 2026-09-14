from datetime import timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User, utcnow
from app.services.audit import log_event

from . import bp


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            flash("Acceso temporalmente bloqueado por intentos fallidos. Probá más tarde.", "danger")
            log_event("LOGIN_BLOCKED", "User", user.id, {"email": email}, user.id)
            db.session.commit()
            return render_template("auth/login.html", email=email), 429
        if not user or not user.active or not user.check_password(password):
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    wait_minutes = min(30, 2 ** (user.failed_login_attempts - 5))
                    user.locked_until = now + timedelta(minutes=wait_minutes)
            log_event("LOGIN_FAILED", "User", user.id if user else None, {"email": email}, user.id if user else None)
            db.session.commit()
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("auth/login.html", email=email), 401
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = now
        login_user(user, remember=request.form.get("remember") == "on")
        log_event("LOGIN_SUCCESS", "User", user.id, {}, user.id)
        db.session.commit()
        next_url = request.args.get("next")
        return redirect(next_url if next_url and next_url.startswith("/") else url_for("dashboard.index"))
    return render_template("auth/login.html")


@bp.post("/logout")
@login_required
def logout():
    user_id = current_user.id
    log_event("LOGOUT", "User", user_id, {})
    db.session.commit()
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/recuperar", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        flash("Solicitá al administrador que restablezca tu contraseña temporal.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html")

