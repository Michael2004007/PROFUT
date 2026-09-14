import math
import random
import secrets
from decimal import Decimal

from app.extensions import db
from app.models import Match, Payment, Team, TournamentEntry, TournamentGroup

from .audit import log_event
from .cash import get_open_session
from .notifications import notify_users
from .payments import PAYMENT_METHODS, next_receipt_number
from .reservations import create_reservation


FORMAT_LABELS = {
    "ROUND_ROBIN": "Todos contra todos",
    "GROUPS_KNOCKOUT": "Grupos + eliminación",
    "KNOCKOUT": "Eliminación directa",
}


def ensure_entries(tournament, user_id):
    existing_team_ids = {entry.team_id for entry in tournament.entries}
    created = []
    for team in tournament.teams:
        if team.id not in existing_team_ids:
            entry = TournamentEntry(
                tournament=tournament,
                team=team,
                fee_amount=tournament.registration_fee or 0,
                paid_amount=0,
                payment_status="PENDIENTE" if Decimal(tournament.registration_fee or 0) > 0 else "PAGADA",
                created_by=user_id,
            )
            db.session.add(entry)
            created.append(entry)
    if created:
        db.session.commit()
    return tournament.entries


def _collect_registration(entry, method, user_id, reference="", idempotency_key=None):
    entry = db.session.scalar(
        db.select(TournamentEntry).where(TournamentEntry.id == entry.id).with_for_update().execution_options(populate_existing=True)
    )
    amount = entry.balance
    if amount <= 0:
        entry.payment_status = "PAGADA"
        return None
    cash_session = get_open_session(for_update=True)
    if not cash_session:
        raise ValueError("La caja está cerrada. Podés inscribir como pendiente o abrir la caja para cobrar.")
    if method not in PAYMENT_METHODS:
        raise ValueError("Seleccioná un método de pago válido.")
    key = idempotency_key or secrets.token_urlsafe(24)
    existing = Payment.query.filter_by(idempotency_key=key).first()
    if existing:
        return existing
    payment = Payment(
        receipt_number=next_receipt_number(),
        idempotency_key=key,
        tournament_entry=entry,
        cash_session=cash_session,
        method=method,
        amount=amount,
        reference=reference.strip(),
        user_id=user_id,
    )
    db.session.add(payment)
    entry.paid_amount = Decimal(entry.paid_amount or 0) + amount
    entry.payment_status = "PAGADA"
    return payment


def register_team(tournament, team, user_id, collect=False, method="", reference="", idempotency_key=None):
    if tournament.draw_completed:
        raise ValueError("El sorteo ya se realizó; no se pueden agregar equipos sin reiniciar la estructura.")
    if TournamentEntry.query.filter_by(tournament_id=tournament.id, team_id=team.id).first():
        raise ValueError("El equipo ya está inscripto en este torneo.")
    if team not in tournament.teams:
        tournament.teams.append(team)
    fee = Decimal(tournament.registration_fee or 0)
    entry = TournamentEntry(
        tournament=tournament,
        team=team,
        fee_amount=fee,
        paid_amount=0,
        payment_status="PENDIENTE" if fee > 0 else "PAGADA",
        created_by=user_id,
    )
    db.session.add(entry)
    db.session.flush()
    payment = _collect_registration(entry, method, user_id, reference, idempotency_key) if collect else None
    log_event("TEAM_ENROLLED", "TournamentEntry", entry.id, {
        "tournament_id": tournament.id,
        "team_id": team.id,
        "fee": fee,
        "paid": bool(payment) or fee == 0,
    }, user_id)
    notify_users(
        "Equipo inscripto",
        f"{team.name} fue inscripto en {tournament.name} ({entry.payment_status.lower()}).",
        f"/torneos/{tournament.id}/inscripciones",
        "TORNEO",
    )
    db.session.commit()
    return entry, payment


def pay_registration(entry, method, user_id, reference="", idempotency_key=None):
    payment = _collect_registration(entry, method, user_id, reference, idempotency_key)
    log_event("TOURNAMENT_FEE_PAID", "TournamentEntry", entry.id, {
        "payment_id": payment.id if payment else None,
        "amount": payment.amount if payment else 0,
    }, user_id)
    db.session.commit()
    return payment


def round_robin_rounds(teams):
    participants = list(teams)
    if len(participants) % 2:
        participants.append(None)
    count = len(participants)
    rounds = []
    for round_index in range(count - 1):
        pairings = []
        for index in range(count // 2):
            home = participants[index]
            away = participants[count - 1 - index]
            if home is not None and away is not None:
                if round_index % 2 and index == 0:
                    home, away = away, home
                pairings.append((home, away))
        rounds.append(pairings)
        participants = [participants[0], participants[-1], *participants[1:-1]]
    return rounds


def _round_name(match_count):
    return {1: "Final", 2: "Semifinal", 4: "Cuartos de final", 8: "Octavos de final"}.get(match_count, f"Ronda de {match_count * 2}")


def _advance_winner(match, winner):
    match.winner_team = winner
    if not match.next_match:
        match.tournament.champion = winner
        match.tournament.status = "FINALIZADO"
        return
    if match.next_slot == "HOME":
        match.next_match.home_team = winner
    else:
        match.next_match.away_team = winner
    if match.next_match.home_team and match.next_match.away_team:
        match.next_match.status = "PENDIENTE"


def generate_knockout(tournament, teams):
    teams = list(teams)
    if len(teams) < 2:
        raise ValueError("Se necesitan al menos dos clasificados para crear la llave.")
    if Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT").first():
        return
    bracket_size = 2 ** math.ceil(math.log2(len(teams)))
    first_match_count = bracket_size // 2
    first_pairs = []
    for index in range(first_match_count):
        home = teams[index]
        away_index = bracket_size - 1 - index
        away = teams[away_index] if away_index < len(teams) else None
        first_pairs.append((home, away))

    rounds = []
    match_count = first_match_count
    round_number = 1
    while match_count >= 1:
        round_matches = []
        for position in range(match_count):
            home, away = first_pairs[position] if round_number == 1 else (None, None)
            match = Match(
                tournament=tournament,
                home_team=home,
                away_team=away,
                stage="KNOCKOUT",
                round_number=round_number,
                round_name=_round_name(match_count),
                matchday=round_number,
                bracket_position=position + 1,
                status="PENDIENTE" if home and away else "ESPERANDO",
            )
            db.session.add(match)
            round_matches.append(match)
        db.session.flush()
        rounds.append(round_matches)
        match_count //= 2
        round_number += 1

    for round_index in range(len(rounds) - 1):
        for index, match in enumerate(rounds[round_index]):
            match.next_match = rounds[round_index + 1][index // 2]
            match.next_slot = "HOME" if index % 2 == 0 else "AWAY"

    for match in rounds[0]:
        if match.home_team and not match.away_team:
            match.status = "BYE"
            _advance_winner(match, match.home_team)
    tournament.bracket_generated = True


def draw_tournament(tournament, user_id):
    ensure_entries(tournament, user_id)
    entries = list(tournament.entries)
    if tournament.draw_completed:
        raise ValueError("El torneo ya fue sorteado.")
    if len(entries) < 2:
        raise ValueError("Inscribí al menos dos equipos antes de sortear.")
    random.SystemRandom().shuffle(entries)
    for seed, entry in enumerate(entries, start=1):
        entry.seed = seed

    if tournament.format == "KNOCKOUT":
        generate_knockout(tournament, [entry.team for entry in entries])
    else:
        group_count = 1 if tournament.format == "ROUND_ROBIN" else max(2, min(tournament.group_count, len(entries)))
        groups = []
        for index in range(group_count):
            group = TournamentGroup(tournament=tournament, name=f"Grupo {chr(65 + index)}", position=index + 1)
            db.session.add(group)
            groups.append(group)
        db.session.flush()

        direction = 1
        group_index = 0
        for entry in entries:
            entry.group = groups[group_index]
            if direction == 1 and group_index == group_count - 1:
                direction = -1
            elif direction == -1 and group_index == 0:
                direction = 1
            else:
                group_index += direction

        for group in groups:
            for round_index, pairings in enumerate(round_robin_rounds([entry.team for entry in group.entries]), start=1):
                for home, away in pairings:
                    db.session.add(Match(
                        tournament=tournament,
                        home_team=home,
                        away_team=away,
                        stage="GROUP",
                        group=group,
                        round_number=round_index,
                        round_name=f"Fecha {round_index}",
                        matchday=round_index,
                        status="PENDIENTE",
                    ))
    tournament.draw_completed = True
    tournament.status = "PROGRAMADO"
    log_event("TOURNAMENT_DRAWN", "Tournament", tournament.id, {
        "format": tournament.format,
        "teams": len(entries),
        "groups": tournament.group_count,
    }, user_id)
    notify_users(
        "Sorteo de torneo completado",
        f"{tournament.name}: se generaron grupos, fechas y cruces automáticamente.",
        f"/torneos/{tournament.id}/grupos",
        "TORNEO",
    )
    db.session.commit()
    return tournament


def standings_for_group(group):
    rows = {
        entry.team_id: {
            "team": entry.team, "pj": 0, "pg": 0, "pe": 0, "pp": 0,
            "gf": 0, "gc": 0, "dg": 0, "pts": 0,
        }
        for entry in group.entries
    }
    finished = Match.query.filter_by(group_id=group.id, stage="GROUP", status="FINALIZADO").all()
    for match in finished:
        home = rows[match.home_team_id]
        away = rows[match.away_team_id]
        home["pj"] += 1
        away["pj"] += 1
        home["gf"] += match.home_score
        home["gc"] += match.away_score
        away["gf"] += match.away_score
        away["gc"] += match.home_score
        if match.home_score > match.away_score:
            home["pg"] += 1
            home["pts"] += 3
            away["pp"] += 1
        elif match.away_score > match.home_score:
            away["pg"] += 1
            away["pts"] += 3
            home["pp"] += 1
        else:
            home["pe"] += 1
            away["pe"] += 1
            home["pts"] += 1
            away["pts"] += 1
    for row in rows.values():
        row["dg"] = row["gf"] - row["gc"]
    ordered = sorted(rows.values(), key=lambda row: (-row["pts"], -row["dg"], -row["gf"], -row["pg"], row["team"].name.lower()))
    for position, row in enumerate(ordered, start=1):
        row["position"] = position
    return ordered


def _all_group_matches_complete(tournament):
    group_matches = [match for match in tournament.matches if match.stage == "GROUP"]
    return bool(group_matches) and all(match.status == "FINALIZADO" for match in group_matches)


def _qualified_teams(tournament):
    tables = [standings_for_group(group) for group in tournament.groups]
    qualified = []
    for rank in range(tournament.qualifiers_per_group):
        qualified.extend(table[rank]["team"] for table in tables if len(table) > rank)
    return qualified


def record_result(match, home_score, away_score, user_id, tie_winner_id=None):
    if not match.home_team or not match.away_team:
        raise ValueError("El cruce todavía no tiene los dos equipos definidos.")
    home_score = int(home_score)
    away_score = int(away_score)
    if home_score < 0 or away_score < 0:
        raise ValueError("Los goles no pueden ser negativos.")
    if match.status == "FINALIZADO" and match.next_match and match.next_match.status == "FINALIZADO":
        raise ValueError("No se puede cambiar este resultado porque la ronda siguiente ya terminó.")
    winner = None
    if home_score > away_score:
        winner = match.home_team
    elif away_score > home_score:
        winner = match.away_team
    elif match.stage == "KNOCKOUT":
        if int(tie_winner_id or 0) not in {match.home_team_id, match.away_team_id}:
            raise ValueError("En una llave empatada indicá quién ganó por penales.")
        winner = match.home_team if int(tie_winner_id) == match.home_team_id else match.away_team
    match.home_score = home_score
    match.away_score = away_score
    match.status = "FINALIZADO"
    match.winner_team = winner

    if match.stage == "KNOCKOUT":
        _advance_winner(match, winner)
    elif _all_group_matches_complete(match.tournament):
        if match.tournament.format == "GROUPS_KNOCKOUT" and not match.tournament.bracket_generated:
            generate_knockout(match.tournament, _qualified_teams(match.tournament))
        elif match.tournament.format == "ROUND_ROBIN":
            table = standings_for_group(match.group)
            if table:
                match.tournament.champion = table[0]["team"]
                match.tournament.status = "FINALIZADO"

    log_event("MATCH_RESULT_RECORDED", "Match", match.id, {
        "home_score": home_score,
        "away_score": away_score,
        "winner_id": winner.id if winner else None,
    }, user_id)
    notify_users(
        "Resultado actualizado",
        f"{match.home_team.name} {home_score} - {away_score} {match.away_team.name}.",
        f"/torneos/{match.tournament_id}/partidos",
        "RESULTADO",
    )
    db.session.commit()
    return match


def schedule_existing_match(match, day, start_time, user_id):
    if match.reservation_id:
        raise ValueError("El partido ya tiene un horario reservado.")
    if not match.home_team or not match.away_team:
        raise ValueError("El cruce todavía no tiene los dos equipos definidos.")
    reservation = create_reservation(
        day,
        start_time,
        f"{match.home_team.name} vs. {match.away_team.name}",
        "",
        user_id,
        reservation_type="TORNEO",
        notes=match.tournament.name,
        create_account=False,
        commit=False,
    )
    match.date = day
    match.start_time = start_time
    match.reservation = reservation
    match.status = "PROGRAMADO"
    log_event("MATCH_SCHEDULED", "Match", match.id, {"reservation_id": reservation.id}, user_id)
    db.session.commit()
    return match


def schedule_match(tournament, home_team, away_team, day, start_time, user_id):
    if home_team.id == away_team.id:
        raise ValueError("Un equipo no puede jugar contra sí mismo.")
    if home_team not in tournament.teams or away_team not in tournament.teams:
        raise ValueError("Ambos equipos deben estar inscriptos en el torneo.")
    match = Match(tournament=tournament, home_team=home_team, away_team=away_team, stage="GROUP")
    db.session.add(match)
    db.session.flush()
    return schedule_existing_match(match, day, start_time, user_id)
