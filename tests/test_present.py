from datetime import UTC, datetime

import pytest

from youdrive.ui.present import (
    HomeView,
    Step,
    TripCard,
    candidate_cards,
    chip_texts,
    describe_drafts,
    describe_sync,
    format_distance,
    format_duration,
    format_when,
    next_step,
    route_labels,
    selectable_for_drafts,
    wait_copy,
)


def view(**overrides) -> HomeView:
    base = dict(
        phone_known=True, phone_ok=True, phone_message="",
        trip_count=4, contract_ok=True, gmail_ok=True,
        candidates=2, ready=2, budget_left=3, daily_limit=3,
    )
    base.update(overrides)
    return HomeView(**base)


def card(identifier: int, score: float | None = 80, reason: str = "", claim_id: int | None = None):
    return TripCard(
        id=identifier, started_at=datetime(2026, 9, identifier, tzinfo=UTC),
        score=score, distance_km=8, duration_seconds=23 * 60,
        start_label="départ", end_label="arrivée", reason=reason, screenshot=None,
        claim_id=claim_id, claim_status="draft" if claim_id else None,
        claim_response="", claim_text="",
    )


@pytest.mark.parametrize(("overrides", "step", "button"), [
    ({"phone_known": False, "trip_count": 0, "candidates": 0, "ready": 0}, Step.PHONE, None),
    (
        {"phone_ok": False, "trip_count": 0, "candidates": 0, "ready": 0, "phone_message": "USB"},
        Step.PHONE, None,
    ),
    (
        {
            "phone_ok": False, "trip_count": 0, "candidates": 0, "ready": 0,
            "phone_message": "ADB est introuvable.",
        },
        Step.PHONE, None,
    ),
    ({"trip_count": 0, "candidates": 0, "ready": 0}, Step.READ, "Lire les trajets"),
    ({"candidates": 0, "ready": 0}, Step.CLEAR, "Lire les trajets"),
    ({"candidates": 0, "ready": 0, "phone_ok": False}, Step.CLEAR, None),
    ({"contract_ok": False}, Step.CONTRACT, "Ouvrir les réglages"),
    ({"gmail_ok": False}, Step.GMAIL, "Connecter Gmail"),
    ({"ready": 0}, Step.REASON, None),
    ({"budget_left": 0}, Step.BUDGET, None),
    ({"ready": 2, "budget_left": 1}, Step.DRAFTS, "Préparer 1 brouillon"),
    ({}, Step.DRAFTS, "Préparer 2 brouillons"),
    ({"phone_ok": False, "phone_message": "USB"}, Step.DRAFTS, "Préparer 2 brouillons"),
])
def test_next_step_follows_the_first_missing_piece(overrides, step, button):
    chosen = next_step(view(**overrides))
    assert chosen.step == step
    assert chosen.button == button


def test_missing_phone_and_missing_adb_are_different_messages():
    usb = next_step(view(
        phone_ok=False, trip_count=0, candidates=0, ready=0,
        phone_message="Téléphone USB introuvable.",
    ))
    adb = next_step(view(
        phone_ok=False, trip_count=0, candidates=0, ready=0, phone_message="ADB est introuvable.",
    ))
    assert usb.title == "Branchez le téléphone"
    assert adb.title == "ADB est introuvable"
    assert "YOUDRIVE_ADB" in adb.detail


def test_budget_sentence_agrees_with_the_limit():
    one = next_step(view(budget_left=0, daily_limit=1, ready=1))
    several = next_step(view(budget_left=0, daily_limit=3, ready=1))
    assert "plafond de 1 préparation" in one.detail
    assert "plafond de 3 préparations" in several.detail


def test_chips_name_the_phone_and_the_remaining_budget():
    waiting = chip_texts(view(phone_known=False))
    assert waiting["Téléphone"] == (None, "vérification")
    assert chip_texts(view(budget_left=1))["Budget"] == (True, "1 restante")
    assert chip_texts(view(budget_left=0))["Budget"] == (False, "0 restantes")
    absent = chip_texts(view(phone_ok=False, phone_message="ADB est introuvable."))
    assert absent["Téléphone"] == (False, "ADB absent")


def test_draft_batch_is_the_oldest_ready_within_budget():
    trips = [card(1, reason="  "), card(2, reason="vitesse"), card(3, reason="virage")]
    assert [item.id for item in selectable_for_drafts(trips, 1)] == [2]
    assert selectable_for_drafts(trips, 0) == []


def test_candidates_skip_perfect_scores_unknown_scores_and_claims():
    trips = [card(1, score=100), card(2, score=None), card(3, claim_id=9), card(4, score=70)]
    assert [item.id for item in candidate_cards(trips)] == [4]


def test_formats_use_paris_time_without_inventing_a_distance():
    moment = datetime(2026, 9, 26, 12, 58, tzinfo=UTC)
    assert format_when(moment, "Europe/Paris") == "26 septembre 2026, 14:58"
    assert format_distance(8) == "8 km"
    assert format_distance(None) == "distance inconnue"
    assert format_duration(23 * 60) == "23 min"
    assert format_duration(90 * 60) == "1 h 30"


def test_sync_and_draft_summaries_do_not_carry_an_address():
    sync = describe_sync(4, 1, 2, 1, True)
    done = describe_sync(4, 1, 2, 0, False)
    same = describe_sync(0, 0, 0, 0, True)
    drafts = describe_drafts(1, 2, 3)
    assert sync == (
        "1 nouveau trajet et 2 mis à jour, avec 1 capture de détail. "
        "Le suivant était déjà enregistré."
    )
    assert done == "1 nouveau trajet et 2 mis à jour."
    assert same == "Aucun nouveau trajet. Le plus récent est déjà enregistré."
    assert "1 brouillon créé" in drafts
    assert "adresse" not in sync
    assert "Aucun message envoyé." in drafts


def test_wait_copy_names_the_step_and_keeps_the_trip_count():
    assert wait_copy([]) == ("Un instant.", "Cela peut prendre un moment.")
    assert wait_copy(["Lecture en cours."])[0] == "Lecture des trajets"
    assert wait_copy(["Retour en haut de la liste."])[0] == "Retour en haut de la liste"
    title, detail = wait_copy(["Trajets lus : 1.", "Capture d'un score inférieur à 100."])
    assert title == "Capture d'un score inférieur à 100"
    assert detail.startswith("1 trajet lu.")
    assert "Rue" not in detail
    title, detail = wait_copy(["Trajets lus : 4.", "Trajet déjà connu atteint."])
    assert title == "4 trajets lus"
    assert "déjà enregistré" in detail
    assert wait_copy(["Trajets lus : 0.", "Trajet déjà connu atteint."])[0] == (
        "Aucun nouveau trajet"
    )
    assert wait_copy(["Trajets lus : 2.", "Fin de la liste."]) == (
        "2 trajets lus", "Toute la liste a été lue.",
    )
    assert wait_copy(["Connexion Gmail en cours."])[0] == "Connexion Gmail"


def test_route_labels_ignore_anything_that_is_not_text():
    assert route_labels(None) == ("", "")
    assert route_labels({"start_label": "Rue du départ", "end_label": 3}) == ("Rue du départ", "")
