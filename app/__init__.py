import os
import shutil
from datetime import datetime
from decimal import Decimal

import click
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import text as sql_text

from config import CONFIGS

from .extensions import csrf, db, login_manager, migrate
from .models import Notification, SystemConfig, User, get_config


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    environment = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(CONFIGS.get(environment, CONFIGS["development"]))
    if environment == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY es obligatoria en producción.")
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "warning"

    from .blueprints.auth import bp as auth_bp
    from .blueprints.dashboard import bp as dashboard_bp
    from .blueprints.agenda import bp as agenda_bp
    from .blueprints.pos import bp as pos_bp
    from .blueprints.products import bp as products_bp
    from .blueprints.teams import bp as teams_bp
    from .blueprints.tournaments import bp as tournaments_bp
    from .blueprints.users import bp as users_bp
    from .blueprints.reports import bp as reports_bp
    from .blueprints.settings import bp as settings_bp

    for blueprint in (
        auth_bp, dashboard_bp, agenda_bp, pos_bp, products_bp, teams_bp,
        tournaments_bp, users_bp, reports_bp, settings_bp,
    ):
        app.register_blueprint(blueprint)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.template_filter("pyg")
    def pyg(value):
        amount = Decimal(value or 0)
        return f"G. {amount:,.0f}".replace(",", ".")

    @app.template_filter("shortdate")
    def shortdate(value):
        return value.strftime("%d/%m/%Y") if value else "—"

    @app.context_processor
    def inject_globals():
        from .services.local_time import local_now

        config = get_config() if db.engine else None
        court_now = local_now()
        recent_notifications = []
        unread_notifications = 0
        if current_user.is_authenticated:
            recent_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
            unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {
            "system_config": config, "today": court_now.date(), "now": court_now,
            "current_user": current_user, "recent_notifications": recent_notifications,
            "unread_notifications": unread_notifications,
        }

    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        flash("El formulario venció. Volvé a intentarlo.", "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.get("/health")
    def health():
        try:
            db.session.execute(sql_text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            db.session.rollback()
            return {"status": "error"}, 503

    @app.cli.command("init-db")
    @click.option("--demo/--no-demo", default=True)
    def init_db_command(demo):
        db.create_all()
        if demo:
            from .seed import seed_database
            seed_database()
        click.echo("Base de datos PROFUT inicializada.")

    @app.cli.command("backup-db")
    def backup_db_command():
        """Crea una copia fechada de la base SQLite local."""
        database_url = app.config["SQLALCHEMY_DATABASE_URI"]
        if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
            raise click.ClickException("Este comando local solo admite bases SQLite.")
        source = database_url.removeprefix("sqlite:///")
        source_path = os.path.abspath(source)
        if not os.path.exists(source_path):
            raise click.ClickException("La base de datos todavía no existe.")
        backup_dir = os.path.join(app.root_path, "..", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        target = os.path.join(backup_dir, f"profut-{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(source_path, target)
        click.echo(f"Backup creado: {os.path.abspath(target)}")

    @app.cli.command("bootstrap-production")
    def bootstrap_production_command():
        """Create only the minimum configuration and first administrator."""
        if not db.session.get(SystemConfig, 1):
            db.session.add(SystemConfig(id=1))
        if not User.query.filter_by(role="ADMIN").first():
            email = os.getenv("ADMIN_EMAIL", "").strip().lower()
            password = os.getenv("ADMIN_PASSWORD", "")
            name = os.getenv("ADMIN_NAME", "Administrador PROFUT").strip() or "Administrador PROFUT"
            if not email or "@" not in email:
                raise click.ClickException("ADMIN_EMAIL es obligatorio para crear el primer administrador.")
            if len(password) < 10:
                raise click.ClickException("ADMIN_PASSWORD debe tener al menos 10 caracteres.")
            if User.query.filter_by(email=email).first():
                raise click.ClickException("ADMIN_EMAIL ya pertenece a otro usuario que no es administrador.")
            admin = User(name=name, email=email, role="ADMIN", active=True)
            admin.set_password(password)
            db.session.add(admin)
            click.echo(f"Administrador inicial creado: {email}")
        else:
            click.echo("El administrador inicial ya existe; no se modificó su contraseña.")
        db.session.commit()
        click.echo("Configuración mínima de producción verificada.")

    with app.app_context():
        if app.config.get("AUTO_CREATE_DB"):
            db.create_all()
            if app.config.get("AUTO_SEED"):
                from .seed import seed_database
                seed_database()

    return app
