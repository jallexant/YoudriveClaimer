"""Screen decisions. No phone, no network, no window."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

_READ_COUNT = re.compile(r"Trajets lus : (\d+)\.")

MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)


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
    claim_at: datetime | None
    claim_text: str


@dataclass(frozen=True)
class Snapshot:
    timezone: str
    daily_limit: int
    budget_left: int
    contract_ok: bool
    gmail_ok: bool
    trips: tuple[TripCard, ...]
    gmail_reconnect: bool = False
    default_message: bool = False


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
    gmail_reconnect: bool = False


@dataclass(frozen=True)
class NextStep:
    step: Step
    title: str
    detail: str
    button: str | None
    action: str | None
    send_button: str | None = None


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


def selectable_for_drafts(
    candidates: list[TripCard], budget: int, *, fallback: bool = False,
) -> list[TripCard]:
    if fallback:
        ready = list(candidates)
    else:
        ready = [trip for trip in candidates if trip.reason.strip()]
    if budget < 1:
        return []
    return ready[:budget]


def home_view(
    snapshot: Snapshot, phone_known: bool, phone_ok: bool, phone_message: str,
) -> HomeView:
    candidates = candidate_cards(snapshot.trips)
    if snapshot.default_message:
        ready = len(candidates)
    else:
        ready = sum(bool(trip.reason.strip()) for trip in candidates)
    return HomeView(
        phone_known=phone_known,
        phone_ok=phone_ok,
        phone_message=phone_message,
        trip_count=len(snapshot.trips),
        contract_ok=snapshot.contract_ok,
        gmail_ok=snapshot.gmail_ok,
        gmail_reconnect=snapshot.gmail_reconnect,
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
        if view.gmail_reconnect:
            return NextStep(
                Step.GMAIL, "Reconnectez Gmail",
                "Une page Google va s'ouvrir pour autoriser l'envoi et le libellé.",
                "Reconnecter Gmail", "gmail",
            )
        return NextStep(
            Step.GMAIL, "Connectez Gmail",
            "Une page Google va s'ouvrir. Préparer crée un brouillon, Envoyer transmet le mail.",
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
                "Les brouillons et les envois du jour sont comptés."
            ),
            None, None,
        )
    count = min(view.budget_left, view.ready)
    label = "Préparer 1 brouillon" if count == 1 else f"Préparer {count} brouillons"
    send = "Envoyer 1 mail" if count == 1 else f"Envoyer {count} mails"
    return NextStep(
        Step.DRAFTS, label,
        "Les plus anciens d'abord, dans la limite du jour. Envoyer transmet le mail tout de suite.",
        label, "drafts", send,
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
        "Gmail": _gmail_chip(view),
        "Contrat": (view.contract_ok, "renseigné" if view.contract_ok else "manquant"),
        "Budget": (view.budget_left > 0, budget),
    }


def _gmail_chip(view: HomeView) -> tuple[bool, str]:
    if view.gmail_reconnect:
        return False, "à reconnecter"
    if view.gmail_ok:
        return True, "connecté"
    return False, "à connecter"


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
        return "Réclamé", "yd-state-claimed"
    if card.score is not None and card.score < 100:
        return "Non réclamé", "yd-state-open"
    return "Pas de réclamation", "yd-state-clear"


def listed_claims(trips: tuple[TripCard, ...] | list[TripCard]) -> list[TripCard]:
    """Newest prepared claim first. Claims without a date follow, newest trip first."""
    claimed = [trip for trip in trips if trip.claim_id is not None]
    dated = [trip for trip in claimed if trip.claim_at is not None]
    undated = [trip for trip in claimed if trip.claim_at is None]
    dated.sort(key=lambda trip: (trip.claim_at, trip.id), reverse=True)
    undated.sort(key=lambda trip: (trip.started_at, trip.id), reverse=True)
    return dated + undated


def claim_line(card: TripCard, timezone: str) -> str:
    if card.claim_at is None:
        return "Déjà réclamée"
    return f"Réclamée le {format_when(card.claim_at, timezone)}"


def google_auth_url(url: str) -> str:
    """Keep only a Google authorization page. Anything else is ignored."""
    if not url.startswith("https://accounts.google.com/"):
        return ""
    if any(char.isspace() or char in "\"'<>\\" for char in url):
        return ""
    return url


def wait_copy(lines: list[str], auth_url: str = "") -> tuple[str, str]:
    """Headline and sentence while a local operation is running."""
    latest = lines[-1] if lines else ""
    auth_url = google_auth_url(auth_url)
    count = _latest_read_count(lines)
    if latest.startswith("Trajets lus"):
        return _count_title(count or 0), "La liste défile, des plus récents vers les plus anciens."
    if latest.startswith("Capture"):
        detail = "Le détail du trajet est ouvert sur le téléphone."
        if count is not None:
            detail = f"{_count_title(count)}. {detail}"
        return "Capture d'un score inférieur à 100", detail
    if latest.startswith("Retour en haut"):
        return (
            "Retour en haut de la liste",
            "Les plus récents sont lus en premier. Cela peut prendre un moment.",
        )
    if latest.startswith("Retour à la liste"):
        detail = "La lecture reprend après la capture."
        if count is not None:
            detail = f"{_count_title(count)}. {detail}"
        return "Retour à la liste", detail
    if latest.startswith("Trajet déjà connu"):
        if count:
            return _count_title(count), (
                "Un trajet déjà enregistré est atteint. Les plus anciens ne sont pas relus."
            )
        return (
            "Aucun nouveau trajet",
            "Le trajet affiché est déjà enregistré. Les plus anciens ne sont pas relus.",
        )
    if latest.startswith("Fin de la liste"):
        title = _count_title(count) if count is not None else "Fin de la liste"
        return title, "Toute la liste a été lue."
    if latest.startswith("Enregistrement"):
        title = _count_title(count) if count is not None else "Enregistrement"
        return title, "Écriture sur cet ordinateur. Aucun message n'est envoyé."
    if latest.startswith("Téléphone détecté"):
        return "Téléphone détecté", "YouDrive va s'ouvrir. Laissez l'écran déverrouillé."
    if latest.startswith("Ouverture de YouDrive"):
        return "Ouverture de YouDrive", "L'écran peut mettre un moment à s'afficher."
    if latest.startswith("L'écran"):
        return (
            "Ouverture de YouDrive",
            "L'écran se charge encore. Laissez le téléphone déverrouillé.",
        )
    if latest.startswith("YouDrive met"):
        return (
            "YouDrive met du temps à s'afficher",
            "Nouvelle tentative d'ouverture. Laissez le téléphone déverrouillé.",
        )
    if latest.startswith("Écran YouDrive"):
        return "YouDrive est ouvert", "Affichage de la liste des trajets."
    if latest.startswith("Liste des trajets"):
        return "Liste des trajets affichée", "Retour en haut, puis lecture des plus récents."
    if latest.startswith("Lecture en cours"):
        return "Lecture des trajets", "Le téléphone reste déverrouillé. Aucun message n'est envoyé."
    if latest.startswith("Connexion Gmail"):
        if auth_url:
            return (
                "Connexion Gmail",
                "Autorisez l'accès dans la page Google. "
                "Si elle ne s'affiche pas, utilisez le bouton. "
                "Aucun message n'est envoyé.",
            )
        return "Connexion Gmail", "Préparation de la page Google. Aucun message n'est envoyé."
    if latest.startswith("Préparation"):
        return "Préparation des brouillons", "Le libellé Gmail est ajouté au brouillon."
    if latest.startswith("Envoi"):
        return "Envoi des mails", "Le service technique YouDrive reçoit le message."
    if not latest:
        return "Un instant.", "Cela peut prendre un moment."
    return latest.rstrip("."), "Cela peut prendre un moment."


def _latest_read_count(lines: list[str]) -> int | None:
    found = None
    for line in lines:
        match = _READ_COUNT.search(line)
        if match:
            found = int(match.group(1))
    return found


def _count_title(count: int) -> str:
    if count == 0:
        return "Aucun trajet lu"
    if count == 1:
        return "1 trajet lu"
    return f"{count} trajets lus"


def describe_sync(
    _read: int, added: int, updated: int, shots: int, reached_known: bool,
) -> str:
    if added == 0 and updated == 0:
        if reached_known:
            return "Aucun nouveau trajet. Le plus récent est déjà enregistré."
        return "Aucun nouveau trajet. Toute la liste a été relue."
    if added and updated:
        body = (
            f"1 nouveau trajet et {updated} mis à jour."
            if added == 1 else f"{added} nouveaux trajets et {updated} mis à jour."
        )
    elif added == 1:
        body = "1 nouveau trajet."
    elif added:
        body = f"{added} nouveaux trajets."
    elif updated == 1:
        body = "1 trajet mis à jour."
    else:
        body = f"{updated} trajets mis à jour."
    if shots == 1:
        body = body[:-1] + ", avec 1 capture de détail."
    elif shots:
        body = body[:-1] + f", avec {shots} captures de détail."
    if reached_known:
        return f"{body} Le suivant était déjà enregistré."
    return body


def describe_drafts(made: int, left: int, limit: int) -> str:
    created = "1 brouillon créé" if made == 1 else f"{made} brouillons créés"
    return (
        f"{created}. Préparations restantes aujourd'hui : {left}/{limit}. "
        "Le libellé adm-voitures-toyota-assurance est ajouté."
    )


def describe_sends(made: int, left: int, limit: int) -> str:
    sent = "1 mail envoyé" if made == 1 else f"{made} mails envoyés"
    return (
        f"{sent}. Préparations restantes aujourd'hui : {left}/{limit}. "
        "Le libellé adm-voitures-toyota-assurance est ajouté."
    )
