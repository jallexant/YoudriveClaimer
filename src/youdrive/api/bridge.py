"""Local receiver for the explicitly installed, passive Chrome relay."""

import hmac
import json
import re
import secrets
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from youdrive.api.visible import parse_visible
from youdrive.api.web import WebError
from youdrive.config import Settings
from youdrive.db.session import initialize_database, open_database
from youdrive.services.sync import import_web_trips

TOKEN_FILE = Path("data/browser-bridge-token.txt")
EXTENSION_DIR = Path("data/browser-extension")


def prepare_extension() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", token):
            raise WebError("Clé du relais local invalide ; vérifiez data/browser-bridge-token.txt.")
    else:
        token = secrets.token_hex(32)
        TOKEN_FILE.write_text(token, encoding="utf-8")
    source = Path(__file__).resolve().parents[3] / "browser-extension"
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    for filename in ("manifest.json", "background.js", "content.js"):
        shutil.copyfile(source / filename, EXTENSION_DIR / filename)
    (EXTENSION_DIR / "local-config.js").write_text(
        f"const LOCAL_TOKEN = {json.dumps(token)};\n", encoding="utf-8",
    )
    return token


def handler_factory(token: str, sessions, lock: threading.Lock):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/trips":
                self.respond(404, {"error": "not_found"})
                return
            authorization = self.headers.get("Authorization", "")
            origin = self.headers.get("Origin", "")
            if not hmac.compare_digest(authorization, f"Bearer {token}") or (
                origin and not re.fullmatch(r"chrome-extension://[a-p]{32}", origin)
            ):
                self.respond(403, {"error": "forbidden"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536 or (
                    self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                ):
                    raise ValueError
                trips = parse_visible(json.loads(self.rfile.read(length)))
            except (ValueError, UnicodeDecodeError, WebError):
                self.respond(400, {"error": "invalid_trip_payload"})
                return
            try:
                with lock, sessions() as session:
                    added, updated = import_web_trips(session, trips)
                    session.commit()
                print(f"Collecte Chrome : {len(trips)} reçus, {added} nouveaux, "
                      f"{updated} actualisés.", flush=True)
                self.respond(200, {"received": len(trips), "added": added, "updated": updated})
            except Exception:
                self.respond(500, {"error": "local_import_failed"})

    return Handler


def serve(settings: Settings) -> None:
    token = prepare_extension()
    engine, sessions = open_database(settings.db_path)
    initialize_database(engine)
    try:
        with ThreadingHTTPServer(
            ("127.0.0.1", 8766), handler_factory(token, sessions, threading.Lock()),
        ) as server:
            print("Relais local prêt sur 127.0.0.1:8766. Extension à charger : "
                  f"{EXTENSION_DIR.resolve()}", flush=True)
            print("Ouvrez ou actualisez normalement votre tableau de bord YouDrive dans Chrome. "
                  "Collecte partielle, sans GPS. Arrêt : Ctrl+C.", flush=True)
            server.serve_forever()
    finally:
        engine.dispose()
