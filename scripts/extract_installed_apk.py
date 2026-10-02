"""Read the official installed package over ADB, without reading account data."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

PACKAGE = "fr.axa.youdrive"


def run_adb(adb: Path, *args: str, timeout: int = 30) -> str:
    result = subprocess.run(
        [str(adb), *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )
    if result.returncode:
        # ADB errors may include a device serial; keep them out of console logs.
        raise RuntimeError("Échec ADB ; vérifier la connexion et les autorisations USB.")
    return result.stdout


def extract(adb: Path, output: Path) -> dict:
    # The user selected the USB phone. ADB -d avoids unrelated Wi-Fi/emulator sessions.
    prefix = ("-d",)
    if run_adb(adb, *prefix, "get-state").strip() != "device":
        raise RuntimeError("Un seul appareil USB ADB autorisé doit être connecté.")
    paths = run_adb(adb, *prefix, "shell", "pm", "path", PACKAGE)
    remote_paths = [line.removeprefix("package:").strip() for line in paths.splitlines()
                    if line.startswith("package:")]
    if not remote_paths or any(not path.endswith(".apk") for path in remote_paths):
        raise RuntimeError("Le package YouDrive installé n'a pas été trouvé.")
    details = run_adb(adb, *prefix, "shell", "dumpsys", "package", PACKAGE)
    version_name = re.search(r"^\s*versionName=(\S+)", details, re.MULTILINE)
    version_code = re.search(r"^\s*versionCode=(\d+)", details, re.MULTILINE)
    android_version = run_adb(adb, *prefix, "shell", "getprop", "ro.build.version.release").strip()
    output.mkdir(parents=True, exist_ok=True)
    files = []
    for index, remote in enumerate(remote_paths):
        # Never reuse a device-controlled path as a local filename.
        filename = "base.apk" if remote.endswith("/base.apk") else f"split-{index:02d}.apk"
        destination = output / filename
        if destination.exists():
            raise RuntimeError("Un APK existe déjà dans ce dossier ; utiliser un dossier neuf.")
        run_adb(adb, *prefix, "pull", remote, str(destination.resolve()), timeout=180)
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"file": filename, "sha256": digest, "bytes": destination.stat().st_size})
    metadata = {
        "package": PACKAGE,
        "version_name": version_name.group(1) if version_name else None,
        "version_code": version_code.group(1) if version_code else None,
        "android_version": android_version,
        "extracted_at": datetime.now(UTC).isoformat(),
        "source": "installed package, read-only ADB extraction",
        "files": files,
    }
    (output / "installation.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("research-private/apk"))
    args = parser.parse_args()
    try:
        metadata = extract(args.adb, args.output)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else "Extraction ADB interrompue."
        print(message)
        return 1
    print(f"YouDrive {metadata['version_name']} (code {metadata['version_code']}), "
          f"Android {metadata['android_version']} ; {len(metadata['files'])} APK extraits.")
    print(f"Dossier local privé : {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
