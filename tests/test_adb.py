import subprocess
from pathlib import Path

import pytest

from youdrive.phone.adb import Adb, adb_executable
from youdrive.phone.errors import PhoneError


def test_commands_target_the_usb_device_only(monkeypatch):
    calls = []

    def run(args, capture_output, timeout, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"device", b"")

    monkeypatch.setattr("youdrive.phone.adb.adb_executable", lambda: "adb")
    monkeypatch.setattr("youdrive.phone.adb.subprocess.run", run)
    Adb().ensure_device()
    assert calls == [["adb", "-d", "get-state"]]


def test_sdk_adb_is_used_when_it_is_absent_from_path(monkeypatch, tmp_path):
    sdk = tmp_path / "Android" / "Sdk" / "platform-tools"
    sdk.mkdir(parents=True)
    executable = sdk / "adb.exe"
    executable.write_text("", encoding="utf-8")
    monkeypatch.delenv("YOUDRIVE_ADB", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("youdrive.phone.adb.shutil.which", lambda _name: None)
    assert adb_executable() == str(executable)
    assert Path(adb_executable()).is_file()


def test_missing_adb_has_a_fixed_message(monkeypatch):
    def run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("youdrive.phone.adb.subprocess.run", run)
    with pytest.raises(PhoneError, match="introuvable") as caught:
        Adb().ensure_device()
    assert "secret" not in str(caught.value)
