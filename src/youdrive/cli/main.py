import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from youdrive.api.android import (
    AndroidError,
    accept_callback,
    login,
    note_callback_error,
    synchronize,
)
from youdrive.config import Settings
from youdrive.db.session import initialize_database, open_database
from youdrive.logging_config import configure_logging
from youdrive.models import Trip
from youdrive.services.sync import import_android_trips
from youdrive.services.trips import (
    list_candidates,
    list_trips,
    remaining_daily_budget,
    summarize,
)


def _auth_callback(rest: list[str]) -> int:
    directory = Path.cwd() / "data"
    url = None
    index = 0
    while index < len(rest):
        item = rest[index]
        if item == "--directory" and index + 1 < len(rest):
            directory = Path(rest[index + 1])
            index += 2
            continue
        cleaned = item.strip().strip("\"'")
        if "fr.axa.youdrive://" in cleaned:
            url = cleaned
        index += 1
    try:
        accept_callback(url, directory)
    except AndroidError as exc:
        note_callback_error(directory, str(exc))
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def print_trips(trips: list[Trip], timezone: str) -> None:
    if not trips:
        print("Aucun trajet.")
        return
    print("ID local | Début | Score | Distance")
    for trip in trips:
        start = trip.started_at.astimezone(ZoneInfo(timezone)).isoformat(timespec="minutes")
        score = f"{trip.score:g}" if trip.score is not None else "inconnu"
        distance = f"{trip.distance_km:g}" if trip.distance_km is not None else "inconnue"
        print(f"{trip.id} | {start} | {score} | {distance}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suivi local des trajets et réclamations YouDrive")
    parser.add_argument(
        "command",
        choices=["init", "login", "auth-callback", "sync", "trips", "candidates", "status"],
    )
    parser.add_argument("callback_url", nargs="?")
    parser.add_argument("--directory", type=Path)
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "auth-callback":
        return _auth_callback(raw[1:])
    args = parser.parse_args(argv)
    if args.callback_url is not None or args.directory is not None:
        print("Argument inattendu.", file=sys.stderr)
        return 2
    engine = None
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        if args.command == "login":
            login(settings)
            print("Connexion enregistrée. Aucun mot de passe n'est conservé.")
            return 0
        incoming = synchronize(settings) if args.command == "sync" else None
        engine, sessions = open_database(settings.db_path)
        initialize_database(engine)
        with sessions() as session:
            now = datetime.now(UTC)
            if incoming is not None:
                added, updated = import_android_trips(session, incoming.trips)
                session.commit()
                print(f"Trajets reçus : {len(incoming.trips)} ; nouveaux : {added} ; "
                      f"actualisés : {updated}.")
                print(f"Contrats lus : {incoming.policy_count}.")
                print_trips(list_trips(session), settings.timezone)
                print("Source : application Android, liste complète sans pagination.")
                print("La distance est le nombre reçu, sans conversion.")
                print("Les trajets web déjà importés sont conservés. Aucune réclamation envoyée.")
            elif args.command == "init":
                print("Base SQLite initialisée.")
            elif args.command == "trips":
                print_trips(list_trips(session), settings.timezone)
            elif args.command == "candidates":
                print_trips(list_candidates(session), settings.timezone)
                budget = remaining_daily_budget(session, settings, now)
                print(f"Budget d'envoi restant aujourd'hui : {budget}/{settings.daily_claim_limit}")
                print("Liste d'éligibilité locale ; aucune réclamation préparée ou envoyée.")
            else:
                summary = summarize(session)
                print(f"Trajets : {summary.trips}")
                print(f"Scores < 100 : {summary.low_scores}")
                print(f"Candidats : {summary.candidates}")
                print(f"Réclamations : {summary.claims}")
                labels = {
                    "draft": "Brouillons", "pending": "En attente", "corrected": "Corrections",
                    "rejected": "Refus", "unknown": "Résultats inconnus",
                }
                for status, label in labels.items():
                    print(f"{label} : {summary.statuses[status]}")
                budget = remaining_daily_budget(session, settings, now)
                print(f"Budget d'envoi restant aujourd'hui : {budget}/{settings.daily_claim_limit}")
        logging.getLogger("youdrive").info("cli.completed")
        return 0
    except KeyboardInterrupt:
        print("Synchronisation arrêtée.")
        return 0
    except AndroidError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 2
    except (SQLAlchemyError, OSError):
        logging.getLogger("youdrive").error("database.failed")
        print("Impossible d'ouvrir ou d'initialiser la base locale. "
              "Vérifiez le chemin et les droits d'accès.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
