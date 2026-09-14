from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Account, Match, Notification, Payment, Product, Team, Tournament, User
from app.services.accounts import add_product, change_product_quantity
from app.services.cash import cash_summary, close_cash, open_cash
from app.services.payments import charge_account, void_payment
from app.services.pos import create_direct_sale
from app.services.reservations import create_reservation, slot_has_passed
from app.services.tournaments import draw_tournament, record_result, register_team, schedule_match, standings_for_group


def tomorrow():
    return date.today() + timedelta(days=1)


def test_reservation_creates_historical_court_account(app):
    with app.app_context():
        admin = User.query.first()
        reservation = create_reservation(tomorrow(), datetime.strptime("09:00", "%H:%M").time(), "Cliente Test", "0981000000", admin.id)
        assert reservation.account is not None
        assert reservation.account.total == Decimal("100000.00")
        assert reservation.account.balance == Decimal("100000.00")
        assert reservation.account.items[0].item_type == "COURT"


def test_double_booking_is_rejected(app):
    with app.app_context():
        admin = User.query.first()
        slot = datetime.strptime("10:00", "%H:%M").time()
        create_reservation(tomorrow(), slot, "Primera", "", admin.id)
        with pytest.raises(ValueError, match="ocup"):
            create_reservation(tomorrow(), slot, "Segunda", "", admin.id)


def test_live_slot_expiration_uses_the_current_local_time(app):
    morning = datetime.strptime("09:00", "%H:%M").time()
    now = datetime.combine(date.today(), datetime.strptime("10:00", "%H:%M").time())
    assert slot_has_passed(date.today(), morning, now=now)
    assert not slot_has_passed(tomorrow(), morning, now=now)


def test_account_quantity_changes_only_after_product_is_added(app):
    with app.app_context():
        admin = User.query.first()
        product = Product.query.first()
        reservation = create_reservation(tomorrow(), datetime.strptime("14:00", "%H:%M").time(), "Cantidad", "", admin.id)
        item = add_product(reservation.account, product, 1, admin.id)
        change_product_quantity(item, 1, admin.id)
        assert item.qty == 2
        assert product.stock == 18
        change_product_quantity(item, -1, admin.id)
        assert item.qty == 1
        assert product.stock == 19


def test_product_consumption_and_partial_payment(app):
    with app.app_context():
        admin = User.query.first()
        product = Product.query.first()
        reservation = create_reservation(tomorrow(), datetime.strptime("11:00", "%H:%M").time(), "Equipo", "", admin.id)
        item = add_product(reservation.account, product, 4, admin.id)
        assert Product.query.first().stock == 16
        cash = open_cash(admin.id, 50000)
        payment = charge_account(reservation.account, {item.id: 20000}, "PIX", admin.id, idempotency_key="partial-test")
        assert payment.amount == Decimal("20000.00")
        assert item.paid_amount == Decimal("20000.00")
        assert reservation.account.status == "PARCIALMENTE_PAGADA"
        assert reservation.account.balance == Decimal("120000.00")
        assert cash_summary(cash)["by_method"]["PIX"] == Decimal("20000.00")


def test_direct_sale_decrements_stock_once_with_idempotency(app):
    with app.app_context():
        admin = User.query.first()
        product = Product.query.first()
        open_cash(admin.id, 0)
        first = create_direct_sale([{"product_id": product.id, "qty": 3}], "EFECTIVO", admin.id, idempotency_key="sale-test")
        second = create_direct_sale([{"product_id": product.id, "qty": 3}], "EFECTIVO", admin.id, idempotency_key="sale-test")
        assert first.id == second.id
        assert Product.query.first().stock == 17


def test_direct_sale_aggregates_duplicate_lines_before_stock_check(app):
    with app.app_context():
        admin = User.query.first()
        product = Product.query.first()
        open_cash(admin.id, 0)
        with pytest.raises(ValueError, match="Stock insuficiente"):
            create_direct_sale([
                {"product_id": product.id, "qty": 12},
                {"product_id": product.id, "qty": 12},
            ], "EFECTIVO", admin.id)
        db.session.rollback()
        assert Product.query.first().stock == 20


def test_cash_close_calculates_difference(app):
    with app.app_context():
        admin = User.query.first()
        product = Product.query.first()
        cash = open_cash(admin.id, 100000)
        create_direct_sale([{"product_id": product.id, "qty": 2}], "EFECTIVO", admin.id, idempotency_key="cash-test")
        closed = close_cash(cash, 121000, admin.id)
        assert closed.expected_cash == Decimal("120000.00")
        assert closed.difference == Decimal("1000.00")
        assert closed.status == "CERRADA"


def test_tournament_match_blocks_agenda_slot(app):
    with app.app_context():
        admin = User.query.first()
        home = Team(name="Local", status="ACTIVO")
        away = Team(name="Visitante", status="ACTIVO")
        tournament = Tournament(name="Copa", start_date=tomorrow())
        tournament.teams.extend([home, away])
        db.session.add(tournament)
        db.session.commit()
        slot = datetime.strptime("12:00", "%H:%M").time()
        match = schedule_match(tournament, home, away, tomorrow(), slot, admin.id)
        assert match.reservation.reservation_type == "TORNEO"
        with pytest.raises(ValueError, match="ocup"):
            create_reservation(tomorrow(), slot, "Cliente", "", admin.id)


def test_reservation_creates_notification(app):
    with app.app_context():
        admin = User.query.first()
        create_reservation(tomorrow(), datetime.strptime("13:00", "%H:%M").time(), "Cliente aviso", "", admin.id)
        notice = Notification.query.filter_by(user_id=admin.id, category="RESERVA").first()
        assert notice is not None
        assert "Cliente aviso" in notice.message


def test_tournament_registration_payment_and_void(app):
    with app.app_context():
        admin = User.query.first()
        open_cash(admin.id, 0)
        tournament = Tournament(name="Copa con cobro", start_date=tomorrow(), registration_fee=150000)
        team = Team(name="Equipo Pagador", status="ACTIVO")
        db.session.add_all([tournament, team])
        db.session.commit()
        entry, payment = register_team(tournament, team, admin.id, collect=True, method="EFECTIVO", idempotency_key="entry-pay")
        assert entry.payment_status == "PAGADA"
        assert entry.balance == 0
        assert payment.tournament_entry_id == entry.id
        void_payment(payment, admin.id)
        assert entry.payment_status == "PENDIENTE"
        assert entry.balance == Decimal("150000.00")


def test_groups_results_standings_and_automatic_final(app):
    with app.app_context():
        admin = User.query.first()
        tournament = Tournament(
            name="Copa grupos", start_date=tomorrow(), format="GROUPS_KNOCKOUT",
            group_count=2, qualifiers_per_group=1,
        )
        teams = [Team(name=f"Equipo {index}", status="ACTIVO") for index in range(1, 5)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        assert len(tournament.groups) == 2
        group_matches = Match.query.filter_by(tournament_id=tournament.id, stage="GROUP").all()
        assert len(group_matches) == 2
        for match in group_matches:
            record_result(match, 2, 0, admin.id)
            table = standings_for_group(match.group)
            assert table[0]["pts"] == 3
        final = Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT").one()
        assert final.home_team is not None and final.away_team is not None
        record_result(final, 1, 1, admin.id, tie_winner_id=final.home_team_id)
        assert tournament.champion_team_id == final.home_team_id
        assert tournament.status == "FINALIZADO"


def test_two_group_playoffs_cross_first_against_other_group_second(app):
    with app.app_context():
        admin = User.query.first()
        tournament = Tournament(
            name="Cruces", start_date=tomorrow(), format="GROUPS_KNOCKOUT",
            group_count=2, qualifiers_per_group=2,
        )
        teams = [Team(name=f"Club {index}", status="ACTIVO") for index in range(1, 9)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        for match in Match.query.filter_by(tournament_id=tournament.id, stage="GROUP").all():
            record_result(match, 1 if match.id % 2 else 2, 0, admin.id)
        first_round = Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT", round_number=1).all()
        assert len(first_round) == 2
        entry_groups = {entry.team_id: entry.group_id for entry in tournament.entries}
        assert all(entry_groups[match.home_team_id] != entry_groups[match.away_team_id] for match in first_round)


def test_round_robin_generates_every_match_and_declares_champion(app):
    with app.app_context():
        admin = User.query.first()
        tournament = Tournament(name="Liga completa", start_date=tomorrow(), format="ROUND_ROBIN")
        teams = [Team(name=f"Liga {index}", status="ACTIVO") for index in range(1, 6)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        matches = Match.query.filter_by(tournament_id=tournament.id, stage="GROUP").all()
        assert len(tournament.groups) == 1
        assert len(matches) == 10
        for match in matches:
            record_result(match, 1, 0, admin.id)
        table = standings_for_group(tournament.groups[0])
        assert all(row["pj"] == 4 for row in table)
        assert tournament.champion_team_id == table[0]["team"].id
        assert tournament.status == "FINALIZADO"


def test_direct_knockout_handles_bye_and_advances_winners(app):
    with app.app_context():
        admin = User.query.first()
        tournament = Tournament(name="Copa directa", start_date=tomorrow(), format="KNOCKOUT")
        teams = [Team(name=f"Directo {index}", status="ACTIVO") for index in range(1, 4)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        first_round = Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT", round_number=1).all()
        final = Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT", round_number=2).one()
        assert len(first_round) == 2
        assert sum(match.status == "BYE" for match in first_round) == 1
        played_semifinal = next(match for match in first_round if match.home_team and match.away_team)
        record_result(played_semifinal, 2, 1, admin.id)
        assert final.home_team is not None and final.away_team is not None
        record_result(final, 0, 0, admin.id, tie_winner_id=final.away_team_id)
        assert tournament.champion_team_id == final.away_team_id
        assert tournament.status == "FINALIZADO"


def test_three_groups_generate_independent_tables_and_playoffs(app):
    with app.app_context():
        admin = User.query.first()
        tournament = Tournament(
            name="Tres grupos", start_date=tomorrow(), format="GROUPS_KNOCKOUT",
            group_count=3, qualifiers_per_group=2,
        )
        teams = [Team(name=f"Tres {index}", status="ACTIVO") for index in range(1, 10)]
        db.session.add_all([tournament, *teams])
        db.session.commit()
        for team in teams:
            register_team(tournament, team, admin.id)
        draw_tournament(tournament, admin.id)
        assert len(tournament.groups) == 3
        assert all(len(group.entries) == 3 for group in tournament.groups)
        group_matches = Match.query.filter_by(tournament_id=tournament.id, stage="GROUP").all()
        assert len(group_matches) == 9
        for match in group_matches:
            record_result(match, 1, 0, admin.id)
        first_round = Match.query.filter_by(tournament_id=tournament.id, stage="KNOCKOUT", round_number=1).all()
        assert tournament.bracket_generated is True
        assert len(first_round) == 4
        assert sum(match.status == "BYE" for match in first_round) == 2
