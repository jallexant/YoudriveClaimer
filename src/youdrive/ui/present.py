"""Screen decisions. No phone, no network, no window."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)

STATUS_LABELS = {
    "draft": "Brouillon",
    "pending": "En attente",
    "corrected": "Correction",
    "rejected": "Refus",
    "unknown": "Résultat inconnu",
}


class Step(StrEnum):
    PHONE = "phone"
    READ = "read"
    CONTRACT = "contract"
    GMAIL = "gmail"
    REASON = "reason"
    DRAFTS = "drafts"
    BUDGET = "budget"
    CLEAR = "clear"


@dataclass(frozen=True)
class TripCard:
    id: int
    started_at: datetime
    score: float | None
    distance_km: float | None
    duration_seconds: int | None
    start_label: str
    end_label: str
    reason: str
    screenshot: str | None
    claim_id: int | None
    claim_status: str | None
    claim_response: str
    claim_text: str


@dataclass(frozen=True)
class Snapshot:
    timezone: str
    daily_limit: int
    budget_left: int
    contract_ok: bool
    gmail_ok: bool
    trips: tuple[TripCard, ...]


@dataclass(frozen=True)
class HomeView:
    phone_known: bool
    phone_ok: bool
    phone_message: str
    trip_count: int
    contract_ok: bool
    gmail_ok: bool
    candidates: int
    ready: int
    budget_left: int
    daily_limit: int


@dataclass(frozen=True)
class NextStep:
    step: Step
    title: str
    detail: str
    button: str | None
    action: str | None


def route_labels(gps: object) -> tuple[str, str]:
    if not isinstance(gps, dict):
        return "", ""
    start = gps.get("start_label")
    end = gps.get("end_label")
    return (start if isinstance(start, str) else "", end if isinstance(end, str) else "")


def route_line(start: str, end: str) -> str:
    if start and end:
        return f"{start} → {end}"
    return start or end


def candidate_cards(trips: tuple[TripCard, ...] | list[TripCard]) -> list[TripCard]:
    """Oldest first, same order as the trips already are."""
    return [
        trip for trip in trips
        if trip.score is not None and trip.score < 100 and trip.claim_id is None
    ]


def selectable_for_drafts(candidates: list[TripCard], budget: int) -> list[TripCard]:
    ready = [trip for trip in candidates if trip.reason.strip()]
    if budget < 1:
        return []
    return ready[:budget]


def home_view(
    snapshot: Snapshot, phone_known: bool, phone_ok: bool, phone_message: str,
) -> HomeView:
    candidates = candidate_cards(snapshot.trips)
    ready = sum(bool(trip.reason.strip()) for trip in candidates)
    return HomeView(
        phone_known=phone_known,
        phone_ok=phone_ok,
        phone_message=phone_message,
        trip_count=len(snapshot.trips),
        contract_ok=snapshot.contract_ok,
        gmail_ok=snapshot.gmail_ok,
        candidates=len(candidates),
        ready=ready,
        budget_left=snapshot.budget_left,
        daily_limit=snapshot.daily_limit,
    )


def next_step(view: HomeView) -> NextStep:
    if view.trip_count == 0 and not view.phone_known:
        return NextStep(
            Step.PHONE, "Vérification du téléphone", "Cela prend un instant.", None, None,
        )
    if view.trip_count == 0 and not view.phone_ok:
        if "ADB" in view.phone_message:
            return NextStep(
                Step.PHONE, "ADB est introuvable",
                "Installez les platform-tools Android, ou indiquez YOUDRIVE_ADB.",
                None, None,
            )
        return NextStep(
            Step.PHONE, "Branchez le téléphone",
            "Déverrouillez-le, autorisez le débogage USB, et laissez YouDrive déjà connecté.",
            None, None,
        )
    if view.trip_count == 0:
        return NextStep(
            Step.READ, "Lire les trajets du téléphone",
            "Le téléphone reste déverrouillé pendant la lecture.",
            "Lire les trajets", "read",
        )
    if view.candidates == 0:
        detail = "Les scores inférieurs à 100 ont déjà une réclamation, ou il n'y en a pas."
        if view.phone_ok:
            return NextStep(
                Step.CLEAR, "Aucun trajet à réclamer", detail, "Lire les trajets", "read",
            )
        return NextStep(
            Step.CLEAR, "Aucun trajet à réclamer",
            f"{detail} Branchez le téléphone pour en lire de nouveaux.",
            None, None,
        )
    if not view.contract_ok:
        return NextStep(
            Step.CONTRACT, "Indiquez le numéro de contrat",
            "Il apparaît dans l'objet et la première ligne du brouillon.",
            "Ouvrir les réglages", "settings",
        )
    if not view.gmail_ok:
        return NextStep(
            Step.GMAIL, "Connectez Gmail",
            "Une fenêtre Google va s'ouvrir. Seuls des brouillons seront créés.",
            "Connecter Gmail", "gmail",
        )
    if view.ready == 0:
        return NextStep(
            Step.REASON, "Écrivez le motif",
            "Regardez la capture, puis décrivez le trajet. Le texte est ajouté sous la date.",
            None, None,
        )
    if view.budget_left == 0:
        quota = "1 préparation" if view.daily_limit == 1 else f"{view.daily_limit} préparations"
        return NextStep(
            Step.BUDGET, "C'est fait pour aujourd'hui",
            (
                f"Le plafond de {quota} est atteint. "
                "Ouvrez Gmail, vérifiez les brouillons, et envoyez-les vous-même."
            ),
            None, None,
        )
    count = min(view.budget_left, view.ready)
    label = "Préparer 1 brouillon" if count == 1 else f"Préparer {count} brouillons"
    return NextStep(
        Step.DRAFTS, label,
        "Les plus anciens d'abord, dans la limite du jour. Vous enverrez vous-même depuis Gmail.",
        label, "drafts",
    )


def chip_texts(view: HomeView) -> dict[str, tuple[bool | None, str]]:
    if not view.phone_known:
        phone = (None, "vérification")
    elif view.phone_ok:
        phone = (True, "branché")
    elif "ADB" in view.phone_message:
        phone = (False, "ADB absent")
    else:
        phone = (False, "à brancher")
    if view.budget_left == 1:
        budget = "1 restante"
    else:
        budget = f"{view.budget_left} restantes"
    return {
        "Téléphone": phone,
        "Gmail": (view.gmail_ok, "connecté" if view.gmail_ok else "à connecter"),
        "Contrat": (view.contract_ok, "renseigné" if view.contract_ok else "manquant"),
        "Budget": (view.budget_left > 0, budget),
    }


def format_when(moment: datetime, timezone: str) -> str:
    local = moment.astimezone(ZoneInfo(timezone))
    month = MONTHS[local.month - 1]
    return f"{local.day} {month} {local.year}, {local:%H:%M}"


def format_day(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def format_score(score: float | None) -> str:
    if score is None:
        return "inconnu"
    return f"{score:g}"


def format_distance(km: float | None) -> str:
    if km is None:
        return "distance inconnue"
    return f"{km:g} km"


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "durée inconnue"
    minutes, _rest = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d}"
    return f"{minutes} min"


def score_class(score: float | None) -> str:
    if score is None:
        return "yd-score-unknown"
    if score >= 100:
        return "yd-score-ok"
    return "yd-score-low"


def trip_state(card: TripCard) -> tuple[str, str]:
    if card.claim_status:
        return STATUS_LABELS.get(card.claim_status, card.claim_status), "yd-hint"
    if card.score is not None and card.score < 100:
        return "À réclamer", "yd-score-low"
    return "Rien à préparer", "yd-hint"


def describe_sync(read: int, added: int, updated: int, shots: int, reached_known: bool) -> str:
    end = (
        "Arrêt au premier trajet déjà en base."
        if reached_known else "Fin de la liste atteinte."
    )
    return (
        f"Trajets lus : {read}. Nouveaux : {added}. "
        f"Actualisés : {updated}. Captures : {shots}. {end} "
        "Aucun message envoyé."
    )


def describe_drafts(made: int, left: int, limit: int) -> str:
    created = "1 brouillon créé" if made == 1 else f"{made} brouillons créés"
    return (
        f"{created}. Préparations restantes aujourd'hui : {left}/{limit}. "
        "Ouvrez Gmail pour les vérifier. Aucun message envoyé."
    )
