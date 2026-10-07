"""Local YouDrive screen. Bound to this computer. Nothing is sent."""

import logging
import re
import sys
import threading
from dataclasses import dataclass, replace
from datetime import date
from functools import partial

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui
from sqlalchemy.exc import SQLAlchemyError

from youdrive.claims.errors import GmailError
from youdrive.claims.gmail import token_path
from youdrive.claims.letters import build_message
from youdrive.legacy import remove_legacy_auth_protocol
from youdrive.logging_config import configure_logging
from youdrive.models import Trip
from youdrive.phone.errors import PhoneError
from youdrive.ui.actions import (
    connect_gmail,
    create_ready_drafts,
    current_settings,
    handle_trip,
    load_snapshot,
    mark_before,
    phone_status,
    remember_reason,
    save_claim,
    sync_phone,
    write_preferences,
)
from youdrive.ui.present import (
    STATUS_LABELS,
    HomeView,
    NextStep,
    Snapshot,
    TripCard,
    candidate_cards,
    chip_texts,
    describe_drafts,
    describe_sync,
    format_day,
    format_distance,
    format_duration,
    format_score,
    format_when,
    home_view,
    next_step,
    route_line,
    score_class,
    selectable_for_drafts,
    trip_state,
)
from youdrive.ui.theme import install_theme, page_heading, shell

PORT = 8765
_SHOT = re.compile(r"[0-9a-f]{64}\.png")


class Workspace:
    def __init__(self) -> None:
        self.busy = False
        self.progress: list[str] = []
        self.message = ""
        self.error = ""
        self.phone_ok = False
        self.phone_known = False
        self.phone_message = ""
        self.phone_token: object | None = None
        self.generation = 0
        self._lock = threading.Lock()

    def reset_progress(self) -> None:
        with self._lock:
            self.progress = []

    def push(self, line: str) -> None:
        with self._lock:
            self.progress.append(line)

    def lines(self) -> list[str]:
        with self._lock:
            return list(self.progress)


workspace = Workspace()


@dataclass
class JobResult:
    skipped: bool
    result: object
    error: Exception | None


@app.get("/captures/{name}")
def capture(name: str) -> FileResponse:
    if _SHOT.fullmatch(name) is None:
        raise HTTPException(status_code=404)
    settings = current_settings()
    root = (settings.db_path.parent / "screenshots").resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")


def show_error(exc: Exception) -> None:
    if isinstance(exc, (PhoneError, GmailError, ValueError)):
        workspace.error = str(exc)
    elif isinstance(exc, (SQLAlchemyError, OSError)):
        workspace.error = (
            "Impossible d'ouvrir ou d'initialiser la base locale. "
            "Vérifiez le chemin et les droits d'accès."
        )
    else:
        logging.getLogger("youdrive").error("ui.failed")
        workspace.error = "L'opération a échoué."
    workspace.message = ""


def paint_notices() -> None:
    if workspace.error:
        ui.label(workspace.error).classes("yd-alert")
    elif workspace.message:
        ui.label(workspace.message).classes("yd-success")


def paint_chips(view: HomeView) -> None:
    icons = {"Téléphone": "smartphone", "Gmail": "mail_outline",
             "Contrat": "description", "Budget": "savings"}
    for label, (ok, text) in chip_texts(view).items():
        if ok is None:
            kind = "yd-chip-wait"
        elif ok:
            kind = "yd-chip-ok"
        else:
            kind = "yd-chip-bad"
        with ui.element("div").classes(f"yd-chip {kind}"):
            ui.icon(icons[label]).classes("yd-chip-icon").props('aria-hidden="true"')
            with ui.column().classes("yd-chip-copy"):
                ui.label(label).classes("yd-chip-label")
                ui.label(text).classes("yd-chip-value")


def paint_wait() -> None:
    ui.label("Un instant.").classes("yd-title")
    ui.linear_progress().props("indeterminate").style("width: 100%")
    box = ui.column()
    generation = workspace.generation

    def pump(generation: int = generation, box=box) -> None:
        if generation != workspace.generation:
            return
        box.clear()
        with box:
            for line in workspace.lines()[-6:]:
                ui.label(line).classes("yd-muted")

    pump()
    ui.timer(0.4, pump)


def paint_hero(step: NextStep, on_primary) -> None:
    with ui.element("section").classes("yd-hero"):
        with ui.column().classes("yd-hero-copy"):
            ui.label(step.title).classes("yd-title")
            ui.label(step.detail).classes("yd-lead")
            if step.button and not workspace.busy:
                ui.button(step.button, on_click=on_primary).props("unelevated no-caps").classes(
                    "yd-button",
                )
        icon = {"phone": "smartphone", "read": "sync", "contract": "description",
                "gmail": "mail_outline", "reason": "edit_note", "drafts": "drafts",
                "budget": "savings", "clear": "task_alt"}[step.step]
        ui.icon(icon).classes("yd-hero-icon").props('aria-hidden="true"')


def paint_score(score: float | None) -> None:
    with ui.element("div").classes(f"yd-score {score_class(score)}"):
        ui.label(format_score(score))
        if score is not None:
            ui.label("/100").classes("yd-score-scale")


def show_letter(title: str, body: str, screenshot: str | None, note: str | None) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("yd-dialog").props("flat"):
        ui.label(title).classes("yd-title")
        ui.label(body).classes("yd-pre")
        if screenshot:
            ui.image(f"/captures/{screenshot}").classes("yd-shot yd-shot-large")
        if note:
            ui.label(note).classes("yd-hint")
        ui.button("Fermer", on_click=dialog.close).props("flat no-caps")
    dialog.open()


def ask(title: str, body: str, confirm_label: str, on_yes) -> None:
    dialog = ui.dialog()

    async def accept() -> None:
        dialog.close()
        result = on_yes()
        if hasattr(result, "__await__"):
            await result

    with dialog, ui.card().classes("yd-dialog").props("flat"):
        ui.label(title).classes("yd-title")
        ui.label(body).classes("yd-pre")
        with ui.row().classes("justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button(confirm_label, on_click=accept).props("unelevated no-caps").classes(
                "yd-button",
            )
    dialog.open()


def trip_from(card: TripCard) -> Trip:
    gps: dict[str, str] = {}
    if card.start_label:
        gps["start_label"] = card.start_label
    if card.end_label:
        gps["end_label"] = card.end_label
    if card.screenshot:
        gps["screenshot"] = card.screenshot
    return Trip(
        youdrive_id="phone:preview",
        started_at=card.started_at,
        score=card.score,
        distance_km=card.distance_km,
        duration_seconds=card.duration_seconds,
        reason=card.reason or None,
        gps=gps or None,
    )


async def run_job(label: str, work, redraw) -> JobResult:
    if workspace.busy:
        return JobResult(True, None, None)
    workspace.busy = True
    workspace.error = ""
    workspace.message = ""
    workspace.reset_progress()
    workspace.push(label)
    redraw()
    try:
        return JobResult(False, await run.io_bound(work), None)
    except Exception as exc:
        show_error(exc)
        return JobResult(False, None, exc)
    finally:
        workspace.busy = False


def load_screen() -> Snapshot | None:
    try:
        return load_snapshot()
    except (SQLAlchemyError, OSError, ValueError) as exc:
        show_error(exc)
        return None


class HomePage:
    def __init__(self) -> None:
        install_theme()
        self.fields: dict[int, object] = {}
        self.chips = None
        self.hero = None
        self._data: Snapshot | None = None
        self.step: NextStep | None = None
        self.root = ui.column().classes("yd-shell")
        self.token = object()
        workspace.phone_token = self.token
        self.draw()
        ui.timer(0.05, self.probe, once=True)

    def draw(self) -> None:
        if workspace.phone_token is not self.token:
            return
        try:
            self._draw()
        except RuntimeError:
            return

    def _draw(self) -> None:
        workspace.generation += 1
        self.fields.clear()
        self.chips = None
        self.hero = None
        self._data = load_screen()
        self.root.clear()
        with self.root:
            self.paint()

    def paint(self) -> None:
        with shell("home"):
            page_heading(
                "Mes réclamations de score",
                "Retrouvez vos trajets et préparez vos brouillons en toute simplicité.",
            )
            paint_notices()
            if self._data is None:
                return
            self.chips = ui.row().classes("yd-chips")
            self.hero = ui.column().style("width: 100%; gap: 0")
            if workspace.busy:
                self.fill_waiting()
                return
            self.fill_status()
            self.paint_rest()

    def fill_status(self) -> None:
        if workspace.busy or self._data is None or self.chips is None or self.hero is None:
            return
        view = home_view(
            self._data, workspace.phone_known, workspace.phone_ok, workspace.phone_message,
        )
        self.step = next_step(view)
        self.chips.clear()
        self.hero.clear()
        with self.chips:
            paint_chips(view)
        with self.hero:
            paint_hero(self.step, self.on_primary)

    def fill_waiting(self) -> None:
        if self._data is None or self.chips is None or self.hero is None:
            return
        view = home_view(
            self._data, workspace.phone_known, workspace.phone_ok, workspace.phone_message,
        )
        self.chips.clear()
        with self.chips:
            paint_chips(view)
        self.hero.clear()
        with self.hero, ui.element("section").classes("yd-hero"):
            paint_wait()

    async def probe(self) -> None:
        try:
            message = await run.io_bound(phone_status)
        except Exception:
            logging.getLogger("youdrive").error("ui.failed")
            message = "Téléphone USB introuvable."
        if workspace.phone_token is not self.token:
            return
        workspace.phone_known = True
        workspace.phone_ok = message is None
        workspace.phone_message = message or ""
        if workspace.busy:
            return
        if self.fields:
            self.fill_status()
            return
        self.draw()

    async def on_primary(self) -> None:
        if self.step is None:
            return
        if self.step.action == "read":
            await self.begin(False)
        elif self.step.action == "settings":
            ui.navigate.to("/reglages")
        elif self.step.action == "gmail":
            await self.begin_gmail()
        elif self.step.action == "drafts":
            self.ask_drafts()

    def paint_rest(self) -> None:
        if self._data is None or self.step is None:
            return
        candidates = candidate_cards(self._data.trips)
        if candidates:
            with ui.column().classes("yd-section-head"):
                ui.label("À réclamer").classes("yd-section")
                ui.label("Les plus anciens d'abord.").classes("yd-hint")
            with ui.element("div").classes("yd-card-grid"):
                for card in candidates:
                    self.paint_candidate(card)
        async def read_again() -> None:
            await self.begin(False)

        with ui.row().classes("yd-secondary"):
            if self.step.action != "read":
                ui.button("Lire les trajets", on_click=read_again).props("flat no-caps")
            ui.button("Relire toute la liste", on_click=self.ask_full).props("flat no-caps")

    def paint_candidate(self, card: TripCard) -> None:
        zone = self._data.timezone if self._data is not None else "Europe/Paris"
        with ui.card().classes("yd-card").props("flat"):
            with ui.row().classes("yd-card-top"):
                ui.label(format_when(card.started_at, zone)).classes("yd-when")
                paint_score(card.score)
            distance = format_distance(card.distance_km)
            ui.label(f"{distance} · {format_duration(card.duration_seconds)}")
            route = route_line(card.start_label, card.end_label)
            if route:
                ui.label(route).classes("yd-route")
            if card.screenshot:
                ui.image(f"/captures/{card.screenshot}").classes("yd-shot")
            field = ui.textarea(label="Motif", value=card.reason).props("outlined autogrow")
            self.fields[card.id] = field
            ui.label("Ajouté sous la date du trajet, dans le brouillon.").classes("yd-hint")
            field.on_value_change(
                lambda _event, trip_id=card.id, field=field: self.keep(trip_id, field),
            )
            with ui.row().classes("yd-card-actions"):
                ui.button(
                    "Voir le mail",
                    on_click=lambda trip_id=card.id, field=field: self.preview(trip_id, field),
                ).props("flat no-caps")
                ui.button(
                    "Déjà traité",
                    on_click=lambda trip_id=card.id: self.ask_done(trip_id),
                ).props("flat no-caps")

    def keep(self, trip_id: int, field) -> None:
        try:
            remember_reason(trip_id, field.value or "")
        except ValueError as exc:
            workspace.error = str(exc)
            ui.notify(str(exc), type="negative")

    def flush(self) -> None:
        for trip_id, field in list(self.fields.items()):
            self.keep(trip_id, field)

    def preview(self, trip_id: int, field) -> None:
        try:
            remember_reason(trip_id, field.value or "")
        except ValueError as exc:
            ui.notify(str(exc), type="negative")
            return
        if self._data is None:
            return
        found = next(
            (item for item in candidate_cards(self._data.trips) if item.id == trip_id), None,
        )
        if found is None:
            return
        card = replace(found, reason=(field.value or "").strip())
        try:
            message, text = build_message(current_settings(), trip_from(card))
        except GmailError as exc:
            ui.notify(str(exc), type="negative")
            return
        body = f"Destinataire : {message['To']}\nObjet : {message['Subject']}\n\n{text}"
        note = None
        if card.screenshot:
            note = "La capture est insérée dans le corps du brouillon."
        show_letter("Brouillon", body, card.screenshot, note)

    def ask_done(self, trip_id: int) -> None:
        ask(
            "Déjà traité",
            "Ce trajet sort des trajets à réclamer. Aucun brouillon n'est créé.",
            "Marquer",
            lambda trip_id=trip_id: self.apply_done(trip_id),
        )

    def apply_done(self, trip_id: int) -> None:
        try:
            self.flush()
            handle_trip(trip_id)
        except (SQLAlchemyError, OSError, ValueError) as exc:
            show_error(exc)
        else:
            workspace.error = ""
            workspace.message = "Trajet marqué comme déjà réclamé. Aucun brouillon créé."
        self.draw()

    def ask_drafts(self) -> None:
        self.flush()
        self._data = load_screen()
        if self._data is None:
            self.draw()
            return
        selected = selectable_for_drafts(
            candidate_cards(self._data.trips), self._data.budget_left,
        )
        if not selected:
            workspace.error = "Écrivez le motif des trajets à préparer."
            workspace.message = ""
            self.draw()
            return
        lines = []
        for card in selected:
            when = format_when(card.started_at, self._data.timezone)
            lines.append(f"{when} — score {format_score(card.score)}")
        ask(
            "Préparer les brouillons",
            "\n".join(lines) + "\n\nAucun message ne sera envoyé.",
            "Créer les brouillons",
            self.run_drafts,
        )

    def ask_full(self) -> None:
        ask(
            "Relire toute la liste",
            "Toute la liste du téléphone est relue. Le téléphone reste déverrouillé. "
            "Les trajets déjà en base sont mis à jour. Aucun message n'est envoyé.",
            "Relire",
            lambda: self.begin(True),
        )

    async def begin(self, full: bool) -> None:
        self.flush()
        job = await run_job(
            "Lecture en cours.", partial(sync_phone, full, workspace.push), self.draw,
        )
        if job.skipped:
            return
        if isinstance(job.error, PhoneError):
            workspace.phone_known = True
            workspace.phone_ok = False
            workspace.phone_message = str(job.error)
        elif job.error is None and isinstance(job.result, tuple):
            workspace.phone_known = True
            workspace.phone_ok = True
            workspace.phone_message = ""
            read, added, updated, shots, reached = job.result
            workspace.message = describe_sync(read, added, updated, shots, reached)
        self.draw()

    async def begin_gmail(self) -> None:
        self.flush()
        job = await run_job(
            "Connexion Gmail en cours. Une fenêtre du navigateur s'ouvre.",
            connect_gmail, self.draw,
        )
        if job.skipped:
            return
        if job.error is None:
            workspace.message = "Connexion Gmail enregistrée. Aucun message envoyé."
        self.draw()

    async def run_drafts(self) -> None:
        self.flush()
        job = await run_job("Préparation des brouillons.", create_ready_drafts, self.draw)
        if job.skipped:
            return
        if job.error is None and isinstance(job.result, tuple):
            made, left, limit = job.result
            workspace.message = describe_drafts(made, left, limit)
        self.draw()


def watch_until_idle(draw) -> None:
    generation = workspace.generation

    def watch(generation: int = generation) -> None:
        if generation != workspace.generation or workspace.busy:
            return
        draw()

    ui.timer(0.4, watch)


@ui.page("/")
def page_home() -> None:
    HomePage()


@ui.page("/trajets")
def page_trips() -> None:
    install_theme()
    root = ui.column().classes("yd-shell")

    def draw() -> None:
        workspace.generation += 1
        data = None if workspace.busy else load_screen()
        root.clear()
        with root, shell("trips"):
            paint_notices()
            if workspace.busy:
                paint_wait()
                watch_until_idle(draw)
                return
            if data is None:
                return
            trips = list(reversed(data.trips))
            page_heading("Mes trajets", "Retrouvez les trajets enregistrés sur cet ordinateur.")
            if not trips:
                with ui.column().classes("yd-empty"):
                    ui.icon("route").classes("text-primary text-3xl")
                    ui.label("Aucun trajet.").classes("yd-lead")
                    ui.label(
                        "Branchez le téléphone, puis lisez la liste depuis l'accueil.",
                    ).classes("yd-hint")
                return
            ui.label("Les plus récents d'abord.").classes("yd-hint")
            with ui.element("div").classes("yd-card-grid"):
                for card in trips:
                    label, kind = trip_state(card)
                    with ui.card().classes("yd-card").props("flat"):
                        with ui.row().classes("yd-card-top"):
                            ui.label(format_when(card.started_at, data.timezone)).classes("yd-when")
                            paint_score(card.score)
                        distance = format_distance(card.distance_km)
                        ui.label(f"{distance} · {format_duration(card.duration_seconds)}")
                        route = route_line(card.start_label, card.end_label)
                        if route:
                            ui.label(route).classes("yd-route")
                        ui.label(label).classes(kind)

    draw()


@ui.page("/reclamations")
def page_claims() -> None:
    install_theme()
    root = ui.column().classes("yd-shell")

    def draw() -> None:
        workspace.generation += 1
        data = None if workspace.busy else load_screen()
        root.clear()
        with root:
            paint_claims(draw, data)

    draw()


def paint_claims(draw, data: Snapshot | None) -> None:
    with shell("claims"):
        paint_notices()
        if workspace.busy:
            paint_wait()
            watch_until_idle(draw)
            return
        page_heading("Mes réclamations", "Le statut et la note restent sur cet ordinateur.")
        if data is None:
            return
        claims = [card for card in reversed(data.trips) if card.claim_id is not None]
        if not claims:
            with ui.column().classes("yd-empty"):
                ui.icon("drafts").classes("text-primary text-3xl")
                ui.label("Aucune réclamation pour l'instant.").classes("yd-lead")
        with ui.element("div").classes("yd-card-grid"):
            for card in claims:
                paint_claim(card, data.timezone, draw)
        ui.label("Déjà réclamés avant une date").classes("yd-section")
        ui.label(
            "Les scores inférieurs à 100, sans réclamation, commencés avant cette date, "
            "passent en résultat inconnu.",
        ).classes("yd-hint")
        date_input = ui.input("Avant le").props("outlined type=date")

        def ask_mark() -> None:
            raw = (date_input.value or "").strip()
            try:
                label = format_day(date.fromisoformat(raw))
            except ValueError:
                workspace.error = "Choisissez une date."
                workspace.message = ""
                draw()
                return
            ask(
                "Déjà réclamés",
                f"Les trajets commencés avant le {label} seront marqués comme déjà réclamés. "
                "Aucun brouillon n'est créé.",
                "Marquer",
                lambda raw=raw: apply_mark(raw),
            )

        def apply_mark(raw: str) -> None:
            try:
                marked = mark_before(raw)
            except (SQLAlchemyError, OSError, ValueError) as exc:
                show_error(exc)
            else:
                workspace.error = ""
                workspace.message = (
                    f"Trajets marqués comme déjà réclamés : {marked}. Aucun brouillon créé."
                )
            draw()

        ui.button("Marquer ces trajets", on_click=ask_mark).props("flat no-caps")


def paint_claim(card: TripCard, timezone: str, draw) -> None:
    with ui.card().classes("yd-card").props("flat"):
        with ui.row().classes("yd-card-top"):
            ui.label(format_when(card.started_at, timezone)).classes("yd-when")
            paint_score(card.score)
        status = ui.select(STATUS_LABELS, value=card.claim_status, label="Statut").props("outlined")
        note = ui.textarea(
            "Réponse de l'assurance", value=card.claim_response,
        ).props("outlined autogrow")
        with ui.row():
            def store(card=card, status=status, note=note) -> None:
                save_one(card, status, note, draw)

            ui.button("Enregistrer", on_click=store).props("unelevated no-caps").classes(
                "yd-button",
            )
            ui.button(
                "Voir le texte",
                on_click=lambda card=card: show_letter(
                    "Texte enregistré",
                    card.claim_text or "Aucun texte enregistré.",
                    card.screenshot,
                    "Ce texte est celui enregistré avec la réclamation.",
                ),
            ).props("flat no-caps")


def save_one(card: TripCard, status, note, draw) -> None:
    if card.claim_id is None or not status.value:
        workspace.error = "Statut inconnu."
        workspace.message = ""
        draw()
        return
    try:
        save_claim(card.claim_id, str(status.value), note.value or "")
    except (SQLAlchemyError, OSError, ValueError) as exc:
        show_error(exc)
    else:
        workspace.error = ""
        workspace.message = "Réclamation enregistrée. Aucun message envoyé."
    draw()


@ui.page("/reglages")
def page_settings() -> None:
    install_theme()
    root = ui.column().classes("yd-shell")

    def draw() -> None:
        workspace.generation += 1
        root.clear()
        with root:
            paint_settings(draw)

    draw()


def paint_settings(draw) -> None:
    settings = None
    if not workspace.busy:
        try:
            settings = current_settings()
        except ValueError as exc:
            show_error(exc)
    with shell("settings"):
        paint_notices()
        if workspace.busy:
            paint_wait()
            watch_until_idle(draw)
            return
        if settings is None:
            return
        page_heading("Mes réglages", "Ces réglages sont enregistrés sur cet ordinateur.")
        with ui.column().classes("yd-form"):
            contract = ui.input(
                "Numéro de contrat", value=settings.contract_number,
            ).props("outlined")
            signature = ui.textarea(
                "Signature du mail", value=settings.mail_signature,
            ).props("outlined autogrow")
            ui.label("Facultative. Elle est ajoutée à la fin du brouillon.").classes("yd-hint")
            limit = ui.number(
                "Préparations maximum par jour", value=settings.daily_claim_limit,
                min=1, max=30, step=1, precision=0,
            ).props("outlined")
            ui.label(
                "Les plus anciens trajets sont préparés dans cette limite, chaque jour.",
            ).classes("yd-hint")
            client = "" if settings.gmail_client_file is None else str(settings.gmail_client_file)
            client_input = ui.input("Fichier client Google (JSON)", value=client).props("outlined")
            connected = token_path(settings).is_file()
            state = "Gmail est connecté." if connected else "Gmail n'est pas connecté."
            ui.label(state).classes("yd-hint")

            def save() -> None:
                raw_limit = limit.value
                try:
                    if raw_limit is None:
                        raise ValueError("YOUDRIVE_DAILY_CLAIM_LIMIT doit être un entier positif.")
                    write_preferences(
                        contract.value or "",
                        signature.value or "",
                        int(raw_limit),
                        client_input.value or "",
                    )
                except (OSError, ValueError) as exc:
                    show_error(exc)
                else:
                    workspace.error = ""
                    workspace.message = "Réglages enregistrés."
                draw()

            async def connect() -> None:
                job = await run_job(
                    "Connexion Gmail en cours. Une fenêtre du navigateur s'ouvre.",
                    connect_gmail, draw,
                )
                if job.skipped:
                    return
                if job.error is None:
                    workspace.message = "Connexion Gmail enregistrée. Aucun message envoyé."
                draw()

            ui.button("Enregistrer", on_click=save).props("unelevated no-caps").classes("yd-button")
            ui.button("Connecter Gmail", on_click=connect).props("flat no-caps")


def run_ui() -> int:
    remove_legacy_auth_protocol()
    try:
        settings = current_settings()
    except ValueError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 1
    configure_logging(settings.log_level)
    ui.run(
        host="127.0.0.1", port=PORT, title="YouDrive",
        reload=False, show=True, language="fr",
    )
    return 0
