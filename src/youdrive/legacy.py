"""Remove the PKCE protocol handler left by the abandoned Android login."""

import sys


def remove_legacy_auth_protocol() -> None:
    if sys.platform != "win32":
        return
    import winreg

    base = r"Software\Classes\fr.axa.youdrive"
    for name in (base + r"\shell\open\command", base + r"\shell\open", base + r"\shell", base):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, name)
        except OSError:
            continue
