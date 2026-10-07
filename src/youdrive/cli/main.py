import argparse
import logging
import sys
import time
from datetime import UTC, date, datetime
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from youdrive.claims.errors import GmailError
from youdrive.config import Settings
from youdrive.db.session import initialize_database, open_database
from youdrive.legacy import remove_legacy_auth_protocol
from youdrive.logging_config import configure_logging
from youdrive.models import Trip
from youdrive.phone.adb import Adb
from youdrive.phone.collect import collect_trips
from youdrive.phone.errors import PhoneError
from youdrive.services.sync import import_phone_trips
from youdrive.services.trips import (
    list_candidates,
    list_trips,
    mark_claimed_before,
    remaining_daily_budget,
    remaining_draft_budget,
    summarize,
)


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
        choices=[
            "init", "sync", "trips", "candidates", "status", "gmail-login", "drafts",
            "mark-claimed", "ui",
        ],
    )
    parser.add_argument(
        "--before", type=date.fromisoformat, metavar="AAAA-MM-JJ",
        help="mark-claimed : trajets commencés avant cette date (heure de Paris)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="sync : relire toute la liste au lieu de s'arrêter au premier trajet connu",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="ui : démarrer le serveur sans ouvrir le navigateur (service Windows)",
    )
    args = parser.parse_args(argv)
    if args.command == "mark-claimed" and args.before is None:
        parser.error("mark-claimed demande --before AAAA-MM-JJ")
    remove_legacy_auth_protocol()
    engine = None
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        if args.command == "ui":
            from youdrive.ui.app import run_ui

            return run_ui(open_browser=not args.no_browser)
        if args.command == "gmail-login":
            from youdrive.claims.gmail import login

            login(settings)
            print("Connexion Gmail enregistrée. Aucun message envoyé.")
            return 0
        incoming = None
        reached_known = False
        engine, sessions = open_database(settings.db_path)
        initialize_database(engine)
        if args.command == "sync":
            known: set[str] = set()
            if not args.full:
                with sessions() as session:
                    known = set(session.scalars(
                        select(Trip.youdrive_id).where(Trip.youdrive_id.like("phone:%"))
                    ))
            incoming, reached_known = collect_trips(
                Adb(), settings.timezone, time.sleep,
                settings.db_path.parent / "screenshots", known,
            )
        with sessions() as session:
            now = datetime.now(UTC)
            if incoming is not None:
                added, updated = import_phone_trips(session, incoming)
                session.commit()
                print(
                    f"Trajets lus : {len(incoming)} ; nouveaux : {added} ; "
                    f"actualisés : {updated}."
                )
                shots = sum(trip.screenshot_name is not None for trip in incoming)
                print(f"Captures de détail : {shots}.")
                print("Source : écran YouDrive via USB.")
                if reached_known:
                    print("Arrêt au premier trajet déjà en base.")
                    print("Les trajets plus anciens ne sont pas relus.")
                else:
                    print("Fin de la liste atteinte.")
                print("Aucune réclamation envoyée.")
                print_trips(list_trips(session), settings.timezone)
            elif args.command == "drafts":
                from youdrive.claims.drafts import prepare_drafts
                from youdrive.claims.gmail import create_draft

                made = prepare_drafts(
                    session, settings, now, lambda message: create_draft(settings, message),
                )
                left = remaining_draft_budget(session, settings, now)
                print(f"Brouillons créés : {made}.")
                print(f"Préparations restantes aujourd'hui : {left}/{settings.daily_claim_limit}.")
                print("Aucun message envoyé.")
            elif args.command == "mark-claimed":
                cutoff = datetime.combine(args.before, dt_time.min, ZoneInfo(settings.timezone))
                marked = mark_claimed_before(session, cutoff)
                session.commit()
                print(f"Trajets marqués comme déjà réclamés : {marked}.")
                print("Aucun brouillon créé, aucun message envoyé.")
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
        print("Opération arrêtée.")
        return 0
    except (PhoneError, GmailError) as exc:
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
