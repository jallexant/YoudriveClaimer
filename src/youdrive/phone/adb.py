"""USB device access. Only `adb -d` is used, so Wi-Fi devices are ignored."""

import os
import shutil
import subprocess
from pathlib import Path

from youdrive.phone.errors import PhoneError


def adb_executable() -> str:
    override = os.environ.get("YOUDRIVE_ADB", "").strip()
    if override:
        return override
    found = shutil.which("adb")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidate = Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
        if candidate.is_file():
            return str(candidate)
    return "adb"


class Adb:
    def __init__(self) -> None:
        self.executable = adb_executable()

    def ensure_device(self) -> None:
        result = self._run(["get-state"])
        if result.returncode != 0 or result.stdout.strip() != b"device":
            raise PhoneError("Téléphone USB introuvable.")

    def launch(self) -> None:
        result = self._run([
            "shell", "monkey", "-p", "fr.axa.youdrive",
            "-c", "android.intent.category.LAUNCHER", "1",
        ])
        if result.returncode != 0:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")

    def dump(self) -> str:
        remote = "/sdcard/window_dump.xml"
        created = self._run(["shell", "uiautomator", "dump", remote])
        if created.returncode != 0:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")
        read = self._run(["exec-out", "cat", remote])
        self._run(["shell", "rm", "-f", remote])
        if read.returncode != 0 or not read.stdout.strip():
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")
        try:
            return read.stdout.decode("utf-8")
        except UnicodeError:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.") from None

    def tap(self, x: int, y: int) -> None:
        result = self._run(["shell", "input", "tap", str(x), str(y)])
        if result.returncode != 0:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")

    def back(self) -> None:
        result = self._run(["shell", "input", "keyevent", "4"])
        if result.returncode != 0:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")

    def screenshot(self, path: Path) -> None:
        remote = "/sdcard/youdrive-detail.png"
        created = self._run(["shell", "screencap", "-p", remote])
        path.parent.mkdir(parents=True, exist_ok=True)
        pulled = self._run(["pull", remote, str(path)])
        self._run(["shell", "rm", "-f", remote])
        if created.returncode != 0 or pulled.returncode != 0 or not path.is_file():
            raise PhoneError("Capture d'écran impossible.")
        if path.stat().st_size < 8:
            path.unlink(missing_ok=True)
            raise PhoneError("Capture d'écran impossible.")

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        result = self._run([
            "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "400",
        ])
        if result.returncode != 0:
            raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                [self.executable, "-d", *args], capture_output=True, timeout=40, check=False,
            )
        except FileNotFoundError:
            raise PhoneError("ADB est introuvable.") from None
        except subprocess.TimeoutExpired:
            raise PhoneError("Téléphone USB introuvable.") from None
