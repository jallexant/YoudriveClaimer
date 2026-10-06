import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

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
        choices=["init", "sync", "trips", "candidates", "status", "gmail-login", "drafts"],
    )
    args = parser.parse_args(argv)
    remove_legacy_auth_protocol()
    engine = None
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        if args.command == "gmail-login":
            from youdrive.claims.gmail import login

            login(settings)
            print("Connexion Gmail enregistrée. Aucun message envoyé.")
            return 0
        incoming = None
        if args.command == "sync":
            incoming = collect_trips(Adb(), settings.timezone, time.sleep)
        engine, sessions = open_database(settings.db_path)
        initialize_database(engine)
        with sessions() as session:
            now = datetime.now(UTC)
            if incoming is not None:
                added, updated = import_phone_trips(session, incoming)
                session.commit()
                print(
                    f"Trajets lus : {len(incoming)} ; nouveaux : {added} ; "
                    f"actualisés : {updated}."
                )
                print("Source : écran YouDrive via USB. Défilement stabilisé.")
                print("Les trajets déjà importés sont conservés. Aucune réclamation envoyée.")
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
