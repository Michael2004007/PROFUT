from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Player, Team
from app.security import permission_required
from app.services.audit import log_event

from . import bp


@bp.get("")
@login_required
@permission_required("teams.view")
def index():
    teams = Team.query.order_by(Team.name).all()
    selected = db.session.get(Team, request.args.get("team", type=int)) if request.args.get("team") else (teams[0] if teams else None)
    return render_template("teams/index.html", teams=teams, team=selected)


@bp.post("/crear")
@login_required
@permission_required("teams.manage")
def create():
    name = request.form.get("name", "").strip()
    if not name:
        flash("El nombre del equipo es obligatorio.", "danger")
        return redirect(url_for("teams.index"))
    team = Team(
        name=name, division=request.form.get("division", "Libre").strip(),
        contact_name=request.form.get("contact_name", "").strip(), phone=request.form.get("phone", "").strip(),
        email=request.form.get("email", "").strip().lower(), status="INCOMPLETO",
    )
    db.session.add(team)
    try:
        db.session.flush()
        log_event("TEAM_CREATED", "Team", team.id, {"name": name}, current_user.id)
        db.session.commit()
        flash("Equipo creado. Podés cargar sus jugadores ahora o más adelante.", "success")
        return redirect(url_for("teams.index", team=team.id))
    except Exception:
        db.session.rollback()
        flash("Ya existe un equipo con ese nombre.", "danger")
        return redirect(url_for("teams.index"))


@bp.post("/<int:team_id>/editar")
@login_required
@permission_required("teams.manage")
def edit(team_id):
    team = db.get_or_404(Team, team_id)
    team.name = request.form.get("name", team.name).strip()
    team.division = request.form.get("division", team.division).strip()
    team.contact_name = request.form.get("contact_name", team.contact_name).strip()
    team.phone = request.form.get("phone", team.phone).strip()
    team.email = request.form.get("email", team.email).strip().lower()
    team.status = request.form.get("status", team.status)
    log_event("TEAM_UPDATED", "Team", team.id, {"status": team.status}, current_user.id)
    db.session.commit()
    flash("Equipo actualizado.", "success")
    return redirect(url_for("teams.index", team=team.id))


@bp.post("/<int:team_id>/jugadores")
@login_required
@permission_required("teams.manage")
def add_player(team_id):
    team = db.get_or_404(Team, team_id)
    name = request.form.get("full_name", "").strip()
    if not name:
        flash("El nombre del jugador es obligatorio.", "danger")
        return redirect(url_for("teams.index", team=team.id))
    birth_date = None
    if request.form.get("birth_date"):
        try:
            birth_date = date.fromisoformat(request.form["birth_date"])
        except ValueError:
            flash("Fecha de nacimiento inválida.", "danger")
            return redirect(url_for("teams.index", team=team.id))
    player = Player(
        team=team, full_name=name, document_number=request.form.get("document_number", "").strip(),
        birth_date=birth_date, jersey_number=request.form.get("jersey_number", type=int),
        position=request.form.get("position", "").strip(),
    )
    db.session.add(player)
    team.status = "ACTIVO"
    db.session.flush()
    log_event("PLAYER_ADDED", "Player", player.id, {"team_id": team.id}, current_user.id)
    db.session.commit()
    flash("Jugador agregado a la lista.", "success")
    return redirect(url_for("teams.index", team=team.id))


@bp.post("/jugador/<int:player_id>/estado")
@login_required
@permission_required("teams.manage")
def toggle_player(player_id):
    player = db.get_or_404(Player, player_id)
    player.active = not player.active
    log_event("PLAYER_STATUS_CHANGED", "Player", player.id, {"active": player.active}, current_user.id)
    db.session.commit()
    return redirect(url_for("teams.index", team=player.team_id))

