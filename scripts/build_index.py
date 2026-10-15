"""
Build the registry's index.json from every entry and its archive, validate it against the schema,
and sign it with REGISTRY_SIGNING_KEY, writing index.json and index.json.sig to the output directory.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from nacl.signing import SigningKey
from packaging.version import Version
from registry import ROOT, download, entry_paths, load_entry, load_publishers, read_archive

SCHEMA_VERSION = 1


def build() -> dict:
    """Return the index."""
    publishers = load_publishers()
    extensions: dict[str, dict] = {}
    for path in entry_paths():
        entry = load_entry(path, publishers)
        archive = read_archive(entry, download(entry["archive_url"]))
        version = {
            "version": entry["version"],
            "archive_url": entry["archive_url"],
            "sha256": entry["sha256"],
            "requires_smarter": archive.smarter.get("requires-smarter"),
            "released_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        }
        current = extensions.setdefault(
            entry["slug"], {"slug": entry["slug"], "publisher": entry["publisher"], "versions": []}
        )
        current["versions"].append(version)
        # the newest version describes the extension.
        if all(Version(entry["version"]) >= Version(other["version"]) for other in current["versions"]):
            license_ = archive.project.get("license")
            current.update(
                display_name=archive.smarter.get("display-name") or entry["slug"].replace("-", " ").title(),
                description=archive.project.get("description", ""),
                homepage=archive.project.get("urls", {}).get("Homepage"),
                license=license_.get("text") if isinstance(license_, dict) else license_,
                docs_rst=archive.docstring,
            )
    for extension in extensions.values():
        extension["versions"].sort(key=lambda version: Version(version["version"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "publishers": list(publishers.values()),
        "extensions": sorted(extensions.values(), key=lambda extension: extension["slug"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="site", help="The directory to write index.json and index.json.sig to.")
    args = parser.parse_args()
    index = build()
    jsonschema.validate(index, json.loads((ROOT / "schema" / "index.schema.json").read_text(encoding="utf-8")))
    data = json.dumps(index, indent=2, sort_keys=True).encode("utf-8")
    key = os.environ.get("REGISTRY_SIGNING_KEY", "")
    if not key:
        print("error: REGISTRY_SIGNING_KEY is not set")
        return 1
    signing_key = SigningKey(base64.b64decode(key))
    public = base64.b64encode(bytes(signing_key.verify_key)).decode()
    if public != (ROOT / "keys" / "registry.pub").read_text(encoding="utf-8").strip():
        print("error: REGISTRY_SIGNING_KEY does not match keys/registry.pub")
        return 1
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.json").write_bytes(data)
    (output / "index.json.sig").write_bytes(base64.b64encode(signing_key.sign(data).signature))
    print(f"{len(index['extensions'])} extensions, {sum(len(e['versions']) for e in index['extensions'])} versions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
