import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Match, Reservation, Team, Tournament, TournamentEntry
from app.security import permission_required
from app.services.audit import log_event
from app.services.local_time import local_today
from app.services.reservations import generate_slots, slot_has_passed
from app.services.tournaments import (
    FORMAT_LABELS,
    draw_tournament,
    ensure_entries,
    pay_registration,
    record_result,
    register_team,
    schedule_existing_match,
    standings_for_group,
)

from . import bp


def _tournament_context(tournament_id, section):
    tournament = db.get_or_404(Tournament, tournament_id)
    ensure_entries(tournament, current_user.id)
    return {
        "tournament": tournament,
        "section": section,
        "format_labels": FORMAT_LABELS,
    }


@bp.get("")
@login_required
@permission_required("tournaments.view")
def index():
    # Compatibility with links made before the full-page tournament redesign.
    tournament_id = request.args.get("tournament", type=int)
    if tournament_id:
        handler = {
            "teams": registrations,
            "groups": groups,
            "matches": matches,
            "bracket": bracket,
        }.get(request.args.get("view"), summary)
        return handler(tournament_id)
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    available_teams = Team.query.filter(Team.status != "INACTIVO").count()
    return render_template(
        "tournaments/index.html",
        tournaments=tournaments,
        available_teams=available_teams,
        format_labels=FORMAT_LABELS,
    )


@bp.get("/nuevo")
@login_required
@permission_required("tournaments.manage")
def new():
    return render_template("tournaments/new.html", format_labels=FORMAT_LABELS)


@bp.get("/<int:tournament_id>/resumen")
@login_required
@permission_required("tournaments.view")
def summary(tournament_id):
    context = _tournament_context(tournament_id, "summary")
    tournament = context["tournament"]
    context.update(
        fee_total=sum((Decimal(entry.fee_amount or 0) for entry in tournament.entries), Decimal("0")),
        paid_total=sum((Decimal(entry.paid_amount or 0) for entry in tournament.entries), Decimal("0")),
    )
    return render_template("tournaments/summary.html", **context)


@bp.get("/<int:tournament_id>/inscripciones")
@login_required
@permission_required("tournaments.view")
def registrations(tournament_id):
    context = _tournament_context(tournament_id, "registrations")
    context["idempotency_key"] = secrets.token_urlsafe(24)
    return render_template("tournaments/registrations.html", **context)


@bp.get("/<int:tournament_id>/inscribir")
@login_required
@permission_required("tournaments.manage")
def enroll_form(tournament_id):
    context = _tournament_context(tournament_id, "registrations")
    tournament = context["tournament"]
    if tournament.draw_completed:
        flash("La inscripción está cerrada porque el torneo ya fue sorteado.", "danger")
        return redirect(url_for("tournaments.registrations", tournament_id=tournament.id))
    context.update(
        teams=Team.query.filter(Team.status != "INACTIVO").order_by(Team.name).all(),
        idempotency_key=secrets.token_urlsafe(24),
    )
    return render_template("tournaments/enroll.html", **context)


@bp.get("/<int:tournament_id>/sorteo")
@login_required
@permission_required("tournaments.manage")
def draw_form(tournament_id):
    context = _tournament_context(tournament_id, "draw")
    return render_template("tournaments/draw.html", **context)


@bp.get("/inscripcion/<int:entry_id>/cobrar")
@login_required
@permission_required("pos.charge")
def pay_entry_form(entry_id):
    entry = db.get_or_404(TournamentEntry, entry_id)
    if entry.balance <= 0:
        flash(f"La inscripción de {entry.team.name} ya está pagada.", "success")
        return redirect(url_for("tournaments.registrations", tournament_id=entry.tournament_id))
    return render_template(
        "tournaments/pay_entry.html",
        entry=entry,
        tournament=entry.tournament,
        section="registrations",
        format_labels=FORMAT_LABELS,
        idempotency_key=secrets.token_urlsafe(24),
    )


@bp.get("/<int:tournament_id>/grupos")
@login_required
@permission_required("tournaments.view")
def groups(tournament_id):
    context = _tournament_context(tournament_id, "groups")
    tournament = context["tournament"]
    context["standings"] = {group.id: standings_for_group(group) for group in tournament.groups}
    return render_template("tournaments/groups.html", **context)


@bp.get("/<int:tournament_id>/partidos")
@login_required
@permission_required("tournaments.view")
def matches(tournament_id):
    context = _tournament_context(tournament_id, "matches")
    return render_template("tournaments/matches.html", **context)


@bp.get("/<int:tournament_id>/llaves")
@login_required
@permission_required("tournaments.view")
def bracket(tournament_id):
    context = _tournament_context(tournament_id, "bracket")
    tournament = context["tournament"]
    knockout_matches = sorted(
        (match for match in tournament.matches if match.stage == "KNOCKOUT"),
        key=lambda match: (match.round_number, match.bracket_position or 0),
    )
    context["bracket_rounds"] = [
        [match for match in knockout_matches if match.round_number == number]
        for number in sorted({match.round_number for match in knockout_matches})
    ]
    return render_template("tournaments/bracket.html", **context)


@bp.get("/partido/<int:match_id>/programar")
@login_required
@permission_required("tournaments.manage")
def schedule_form(match_id):
    match = db.get_or_404(Match, match_id)
    if not match.home_team or not match.away_team:
        flash("El cruce todavía no tiene los dos equipos definidos.", "danger")
        return redirect(url_for("tournaments.matches", tournament_id=match.tournament_id))
    selected_date = request.args.get("date") or max(local_today(), match.tournament.start_date).isoformat()
    try:
        selected_day = date.fromisoformat(selected_date)
    except ValueError:
        abort(404)
    occupied = {
        row.start_time
        for row in Reservation.query.filter_by(date=selected_day, status="RESERVADA").all()
    }
    slots = [
        (start, end)
        for start, end in generate_slots(selected_day)
        if start not in occupied and not slot_has_passed(selected_day, start)
    ]
    return render_template(
        "tournaments/schedule_match.html",
        match=match,
        tournament=match.tournament,
        section="matches",
        format_labels=FORMAT_LABELS,
        selected_day=selected_day,
        slots=slots,
    )


@bp.get("/partido/<int:match_id>/resultado")
@login_required
@permission_required("tournaments.manage")
def result_form(match_id):
    match = db.get_or_404(Match, match_id)
    if not match.home_team or not match.away_team:
        flash("El cruce todavía no tiene los dos equipos definidos.", "danger")
        return redirect(url_for("tournaments.matches", tournament_id=match.tournament_id))
    return render_template(
        "tournaments/result_match.html",
        match=match,
        tournament=match.tournament,
        section="matches",
        format_labels=FORMAT_LABELS,
    )


@bp.post("/crear")
@login_required
@permission_required("tournaments.manage")
def create():
    try:
        tournament_format = request.form.get("format", "ROUND_ROBIN")
        if tournament_format not in FORMAT_LABELS:
            raise ValueError("Formato de torneo inválido.")
        group_count = int(request.form.get("group_count", 2))
        qualifiers = int(request.form.get("qualifiers_per_group", 2))
        if group_count not in {1, 2, 3, 4} or qualifiers not in {1, 2, 3, 4}:
            raise ValueError("La cantidad de grupos o clasificados no es válida.")
        tournament = Tournament(
            name=request.form.get("name", "").strip(),
            start_date=date.fromisoformat(request.form["start_date"]),
            end_date=date.fromisoformat(request.form["end_date"]) if request.form.get("end_date") else None,
            format=tournament_format,
            category=request.form.get("category", "Fútbol 7 - Libre"),
            registration_fee=Decimal(request.form.get("registration_fee", "0")),
            group_count=1 if tournament_format == "ROUND_ROBIN" else group_count,
            qualifiers_per_group=qualifiers,
            status="BORRADOR",
        )
        if not tournament.name or tournament.registration_fee < 0:
            raise ValueError("Revisá el nombre y el monto de inscripción.")
        db.session.add(tournament)
        db.session.flush()
        log_event("TOURNAMENT_CREATED", "Tournament", tournament.id, {
            "name": tournament.name,
            "format": tournament.format,
            "registration_fee": tournament.registration_fee,
        }, current_user.id)
        db.session.commit()
        flash(f"{tournament.name} fue creado. Ya podés inscribir los equipos.", "success")
        return redirect(url_for("tournaments.registrations", tournament_id=tournament.id))
    except (ValueError, KeyError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("tournaments.new"))


@bp.post("/<int:tournament_id>/equipos")
@login_required
@permission_required("tournaments.manage")
def enroll_team(tournament_id):
    tournament = db.get_or_404(Tournament, tournament_id)
    try:
        if request.form.get("team_mode") == "new":
            name = request.form.get("new_team_name", "").strip()
            if not name:
                raise ValueError("Escribí el nombre del nuevo equipo.")
            if Team.query.filter_by(name=name).first():
                raise ValueError("Ya existe un equipo con ese nombre; elegilo en la lista.")
            team = Team(
                name=name,
                division=request.form.get("new_team_division", "Libre").strip() or "Libre",
                contact_name=request.form.get("new_team_contact", "").strip(),
                phone=request.form.get("new_team_phone", "").strip(),
                status="INCOMPLETO",
            )
            db.session.add(team)
            db.session.flush()
            log_event("TEAM_CREATED", "Team", team.id, {"created_during_enrollment": True}, current_user.id)
        else:
            team = db.get_or_404(Team, request.form.get("team_id", type=int))
        entry, payment = register_team(
            tournament,
            team,
            current_user.id,
            collect=request.form.get("collect_payment") == "on",
            method=request.form.get("method", ""),
            reference=request.form.get("reference", ""),
            idempotency_key=request.form.get("idempotency_key"),
        )
        message = f"{team.name} quedó inscripto"
        if payment:
            message += f" y su inscripción de {payment.amount:,.0f} quedó pagada"
        elif entry.balance > 0:
            message += " con el pago pendiente"
        flash(message + ".", "success")
    except (ValueError, KeyError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("tournaments.registrations", tournament_id=tournament.id))


@bp.post("/inscripcion/<int:entry_id>/cobrar")
@login_required
@permission_required("pos.charge")
def pay_entry(entry_id):
    entry = db.get_or_404(TournamentEntry, entry_id)
    try:
        payment = pay_registration(
            entry,
            request.form.get("method", ""),
            current_user.id,
            request.form.get("reference", ""),
            request.form.get("idempotency_key"),
        )
        flash(f"La inscripción de {entry.team.name} quedó pagada. Comprobante {payment.receipt_number}.", "success")
        return redirect(url_for("pos.ticket", payment_id=payment.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("tournaments.registrations", tournament_id=entry.tournament_id))


@bp.post("/<int:tournament_id>/sortear")
@login_required
@permission_required("tournaments.manage")
def draw(tournament_id):
    tournament = db.get_or_404(Tournament, tournament_id)
    try:
        draw_tournament(tournament, current_user.id)
        flash(f"Sorteo de {tournament.name} completado: la estructura y los partidos ya están listos.", "success")
        endpoint = "tournaments.bracket" if tournament.format == "KNOCKOUT" else "tournaments.groups"
        return redirect(url_for(endpoint, tournament_id=tournament.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("tournaments.draw_form", tournament_id=tournament.id))


@bp.post("/<int:tournament_id>/estado")
@login_required
@permission_required("tournaments.manage")
def update_status(tournament_id):
    tournament = db.get_or_404(Tournament, tournament_id)
    status = request.form.get("status", "")
    if status not in {"BORRADOR", "PROGRAMADO", "EN_CURSO", "FINALIZADO", "CANCELADO"}:
        flash("No se pudo actualizar: el estado elegido no es válido.", "danger")
    elif status == "EN_CURSO" and not tournament.draw_completed:
        flash("Primero realizá el sorteo para poder iniciar el torneo.", "danger")
    else:
        tournament.status = status
        log_event("TOURNAMENT_STATUS_CHANGED", "Tournament", tournament.id, {"status": status}, current_user.id)
        db.session.commit()
        flash(f"{tournament.name} ahora figura como {status.replace('_', ' ').lower()}.", "success")
    return redirect(url_for("tournaments.summary", tournament_id=tournament.id))


@bp.post("/partido/<int:match_id>/programar")
@login_required
@permission_required("tournaments.manage")
def schedule_match(match_id):
    match = db.get_or_404(Match, match_id)
    try:
        day = date.fromisoformat(request.form["date"])
        start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
        schedule_existing_match(match, day, start_time, current_user.id)
        flash(
            f"{match.home_team.name} vs. {match.away_team.name} fue programado para el {day.strftime('%d/%m/%Y')} a las {start_time.strftime('%H:%M')}.",
            "success",
        )
    except (ValueError, KeyError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("tournaments.matches", tournament_id=match.tournament_id))


@bp.post("/partido/<int:match_id>/resultado")
@login_required
@permission_required("tournaments.manage")
def result(match_id):
    match = db.get_or_404(Match, match_id)
    try:
        record_result(
            match,
            request.form.get("home_score", 0),
            request.form.get("away_score", 0),
            current_user.id,
            request.form.get("tie_winner_id"),
        )
        flash(
            f"Resultado guardado: {match.home_team.name} {match.home_score} – {match.away_score} {match.away_team.name}. Tabla y llave actualizadas.",
            "success",
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("tournaments.result_form", match_id=match.id))
    return redirect(url_for("tournaments.matches", tournament_id=match.tournament_id))
