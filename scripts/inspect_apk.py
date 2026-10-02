"""Inventory installed APK assets and static URL hostnames, without exposing URL secrets."""

import argparse
import json
import re
import struct
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


def dex_strings(data: bytes) -> list[str]:
    if not data.startswith(b"dex\n"):
        return []
    count, table = struct.unpack_from("<II", data, 56)
    strings = []
    for index in range(count):
        offset = struct.unpack_from("<I", data, table + index * 4)[0]
        while data[offset] & 0x80:
            offset += 1
        offset += 1  # Skip the final byte of the UTF-16 length prefix.
        end = data.index(b"\x00", offset)
        strings.append(data[offset:end].decode("utf-8", errors="replace"))
    return strings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("research-private/apk/static-inventory.json"),
    )
    args = parser.parse_args()
    strings = []
    environment_fields = {}
    native_routes = set()
    with zipfile.ZipFile(args.apk) as archive:
        files = archive.namelist()
        for filename in files:
            if re.fullmatch(r"classes\d*\.dex", filename):
                strings.extend(dex_strings(archive.read(filename)))
        production_env = "assets/flutter_assets/assets/env/.env.production"
        if production_env in files:
            for line in archive.read(production_env).decode("utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip("\"'")
                field = {"value": "redacted"}
                if value.startswith(("https://", "http://")):
                    url = urlsplit(value)
                    field = {"scheme": url.scheme, "hostname": url.hostname,
                             "path": url.path}
                environment_fields[key.strip()] = field
    protocol_markers = set()
    marker_names = {
        "code_challenge", "code_challenge_method", "code_verifier", "S256",
        "refresh_token", "access_token", "id_token", "grant_type", "client_id",
        "redirect_uri", "response_type", "Authorization", "Bearer", "authorization_code",
    }
    sdk_namespaces = sorted({"/".join(value.removeprefix("L").split("/")[:3])
                             for value in strings if value.startswith("L")
                             and value.endswith(";")
                             and re.search("cmtelematics|cambridge|drivewell|sensorflow", value,
                                           re.IGNORECASE)})
    dex_count = len(strings)
    for split in sorted(args.apk.parent.glob("*.apk")):
        with zipfile.ZipFile(split) as archive:
            for filename in archive.namelist():
                if not filename.endswith("/libapp.so"):
                    continue
                native = archive.read(filename)
                for marker in marker_names:
                    if marker.encode("ascii") in native:
                        protocol_markers.add(marker)
                strings.extend(match.decode("ascii") for match in re.findall(
                    rb"https?://[A-Za-z0-9._:/-]+", native,
                ))
                for match in re.findall(rb"/[A-Za-z][A-Za-z0-9_./{}?=-]{0,100}", native):
                    route = match.decode("ascii")
                    if re.search(r"trip|journey|login|auth|score", route, re.IGNORECASE):
                        native_routes.add(route)
    hosts = set()
    for value in strings:
        for match in re.finditer(r"https?://[^\s\"<>]+", value):
            try:
                host = urlsplit(match.group()).hostname
                if host and re.fullmatch(r"[A-Za-z0-9.-]+", host):
                    hosts.add(host.lower())
            except ValueError:
                continue
    inventory = {
        "apk": args.apk.name,
        "assets": [name for name in files if name.startswith("assets/")],
        "dex_string_count": dex_count,
        "static_url_hostnames": sorted(hosts),
        "production_environment_fields": environment_fields,
        "native_route_candidates_unverified": sorted(native_routes),
        "native_protocol_markers_unverified": sorted(protocol_markers),
        "dex_sdk_namespace_candidates": sdk_namespaces,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in inventory.items() if key != "assets"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
