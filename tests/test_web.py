def login(client):
    return client.post("/auth/login", data={"email": "admin@test.local", "password": "segura-123"})


def test_login_and_protected_pages(client):
    from datetime import date, timedelta

    response = login(client)
    assert response.status_code == 302
    tomorrow = date.today() + timedelta(days=1)
    for path in (
        "/", "/agenda", f"/agenda/{tomorrow.year}/{tomorrow.month}",
        f"/agenda/dia/{tomorrow.isoformat()}", "/productos", "/pos",
        "/pos/caja", "/pos/caja/abrir", "/equipos", "/torneos",
        "/torneos/nuevo", "/usuarios", "/reportes", "/configuracion",
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_wrong_password_is_rejected(client):
    response = client.post("/auth/login", data={"email": "admin@test.local", "password": "incorrecta"})
    assert response.status_code == 401
    assert "incorrectos".encode() in response.data


def test_public_404_does_not_fail_without_session(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json == {"status": "ok"}
    response = client.get("/ruta-que-no-existe")
    assert response.status_code == 404
    assert b"No encontramos" in response.data


def test_report_exports(client):
    login(client)
    assert client.get("/reportes/exportar.csv").status_code == 200
    assert client.get("/reportes/exportar.xlsx").status_code == 200
    assert client.get("/reportes/exportar.pdf").status_code == 200


def test_light_theme_persists_across_modules(client):
    login(client)
    response = client.post("/configuracion/tema", json={"theme": "light"})
    assert response.status_code == 200
    assert b'"theme":"light"' in response.data
    assert b'data-theme="light"' in client.get("/productos").data
    assert b'data-theme="light"' in client.get("/torneos").data


def test_product_requires_photo_and_barcode(client):
    from io import BytesIO
    from pathlib import Path

    from PIL import Image
    from app.extensions import db
    from app.models import Product

    login(client)
    rejected = client.post("/productos/crear", data={"name": "Sin foto", "barcode": "123456", "price": "5000", "stock": "1"})
    assert rejected.status_code == 302
    with client.application.app_context():
        assert Product.query.filter_by(name="Sin foto").first() is None
    image = Image.new("RGB", (20, 20), "red")
    buffer = BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    accepted = client.post("/productos/crear", data={
        "name": "Producto con foto", "barcode": "123456789", "category": "Test",
        "price": "5000", "stock": "2", "low_stock_threshold": "1", "active": "on",
        "image": (buffer, "producto.png"),
    }, content_type="multipart/form-data")
    assert accepted.status_code == 302
    with client.application.app_context():
        product = Product.query.filter_by(barcode="123456789").one()
        image_path = Path(client.application.static_folder) / product.image_path
        assert image_path.exists()
        image_path.unlink()
        db.session.delete(product)
        db.session.commit()


def test_settings_form_saves_schedule_notifications_and_theme(client):
    from app.extensions import db
    from app.models import SystemConfig, User

    login(client)
    response = client.post("/configuracion", data={
        "facility_name": "Complejo Test", "court_name": "Cancha Central",
        "description": "Prueba", "timezone": "America/Asuncion", "currency": "PYG",
        "theme": "light", "reservation_price": "125000", "open_time": "09:00",
        "close_time": "23:00", "slot_minutes": "45", "enabled_days": ["0", "2", "4"],
        "pix_key": "123", "pix_holder": "PROFUT", "pix_key_type": "OTRA",
        "ticket_footer": "Gracias", "notify_reservations": "on",
    })
    assert response.status_code == 302
    with client.application.app_context():
        config = db.session.get(SystemConfig, 1)
        user = User.query.filter_by(email="admin@test.local").one()
        assert config.enabled_days == "0,2,4"
        assert config.slot_minutes == 45
        assert config.notify_reservations is True
        assert config.notify_cancellations is False
        assert user.theme == "light"


def test_production_bootstrap_creates_only_initial_admin_and_config(monkeypatch):
    from app import create_app
    from app.extensions import db
    from app.models import SystemConfig, User

    production_app = create_app("testing")
    with production_app.app_context():
        db.create_all()
    monkeypatch.setenv("ADMIN_EMAIL", "inicial@profut.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "Segura-2026!")
    monkeypatch.setenv("ADMIN_NAME", "Administrador Inicial")
    try:
        runner = production_app.test_cli_runner()
        first = runner.invoke(args=["bootstrap-production"])
        second = runner.invoke(args=["bootstrap-production"])
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        with production_app.app_context():
            assert db.session.get(SystemConfig, 1) is not None
            assert User.query.count() == 1
            admin = User.query.one()
            assert admin.email == "inicial@profut.local"
            assert admin.check_password("Segura-2026!")
    finally:
        with production_app.app_context():
            db.session.remove()
            db.drop_all()


def test_tournament_group_match_and_bracket_views_render(client):
    from datetime import date, timedelta

    from app.extensions import db
    from app.models import Match, Team, Tournament, User
    from app.services.tournaments import draw_tournament, record_result, register_team

    login(client)
    with client.application.app_context():
        admin = User.query.first()
        tournament = Tournament(
            name="Render Cup", start_date=date.today() + timedelta(days=1),
            format="GROUPS_KNOCKOUT", group_count=2, qualifiers_per_group=1,
        )
        teams = [Team(name=f"Render {index}", status="ACTIVO") for index in range(4)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        tournament_id = tournament.id
        for match in Match.query.filter_by(tournament_id=tournament.id, stage="GROUP").all():
            record_result(match, 1, 0, admin.id)
    for view in ("summary", "teams", "groups", "matches", "bracket"):
        response = client.get(f"/torneos?tournament={tournament_id}&view={view}")
        assert response.status_code == 200, view
        assert b"Render Cup" in response.data
    for path in (
        f"/torneos/{tournament_id}/resumen",
        f"/torneos/{tournament_id}/inscripciones",
        f"/torneos/{tournament_id}/grupos",
        f"/torneos/{tournament_id}/partidos",
        f"/torneos/{tournament_id}/llaves",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"Render Cup" in response.data
