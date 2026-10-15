"""
Shared code of the registry's scripts: reading entries and publishers, and checking archives.

An entry is one released version of an extension: extensions/<slug>/<version>.yaml.
"""

import ast
import hashlib
import io
import re
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = ROOT / "extensions"
SLUG = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BADGES = {"official", "verified", "community"}
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
ENTRY_FIELDS = {"slug", "version", "publisher", "archive_url", "sha256"}


class RegistryError(Exception):
    """An entry, a publisher or an archive is not valid."""


@dataclass
class Archive:
    """What the index needs from an extension's archive."""

    project: dict
    smarter: dict
    docstring: str


def load_publishers() -> dict[str, dict]:
    """Return the publishers, by id."""
    data = yaml.safe_load((ROOT / "publishers.yaml").read_text(encoding="utf-8")) or {}
    publishers = {}
    for publisher in data.get("publishers", []):
        if set(publisher) - {"id", "name", "url", "badge"} or not publisher.get("id") or not publisher.get("name"):
            raise RegistryError(
                f"publishers.yaml: a publisher needs an id and a name, and nothing else but url and badge: {publisher}"
            )
        if publisher.get("badge", "community") not in BADGES:
            raise RegistryError(f"publishers.yaml: {publisher['id']} has an unknown badge {publisher.get('badge')}")
        if publisher["id"] in publishers:
            raise RegistryError(f"publishers.yaml: {publisher['id']} is listed twice")
        publishers[publisher["id"]] = {"badge": "community", **publisher}
    return publishers


def entry_paths() -> list[Path]:
    """Return every entry's path, sorted."""
    return sorted(EXTENSIONS.glob("*/*.yaml"))


def load_entry(path: Path, publishers: dict[str, dict]) -> dict:
    """Read and check one entry's file, without downloading its archive."""
    entry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    name = path.relative_to(ROOT)
    if set(entry) != ENTRY_FIELDS:
        raise RegistryError(f"{name}: needs exactly {sorted(ENTRY_FIELDS)}, has {sorted(entry)}")
    if not SLUG.match(str(entry["slug"])) or entry["slug"] != path.parent.name:
        raise RegistryError(f"{name}: slug {entry['slug']} must be its directory's name, and a valid slug")
    if str(entry["version"]) != path.stem:
        raise RegistryError(f"{name}: version {entry['version']} must be its file's name")
    if entry["publisher"] not in publishers:
        raise RegistryError(f"{name}: publisher {entry['publisher']} is not in publishers.yaml")
    if not str(entry["archive_url"]).startswith("https://"):
        raise RegistryError(f"{name}: archive_url must be https")
    if not SHA256.match(str(entry["sha256"])):
        raise RegistryError(f"{name}: sha256 must be 64 lowercase hex digits")
    entry["version"] = str(entry["version"])
    return entry


def check_slug_ownership(entries: list[dict]) -> None:
    """A slug belongs to the publisher of its first version: every version must have the same publisher."""
    owners: dict[str, str] = {}
    for entry in entries:
        owner = owners.setdefault(entry["slug"], entry["publisher"])
        if owner != entry["publisher"]:
            raise RegistryError(f"{entry['slug']} belongs to {owner}, not {entry['publisher']}")


def download(url: str) -> bytes:
    """Download an archive, refusing one that is too large."""
    request = urllib.request.Request(url, headers={"User-Agent": "smarter-extensions-registry"})
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310: https only, checked by load_entry
        data = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise RegistryError(f"{url} is larger than {MAX_ARCHIVE_BYTES} bytes")
    return data


def read_archive(entry: dict, data: bytes) -> Archive:
    """Check an archive against its entry, and return its pyproject.toml's tables and its documentation."""
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise RegistryError(f"{entry['slug']} {entry['version']}: the archive's sha256 is not {entry['sha256']}")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise RegistryError(f"{entry['slug']} {entry['version']}: not a zip file") from e
    names = [info.filename for info in archive.infolist() if not info.is_dir()]
    prefix = ""
    if "pyproject.toml" not in names:
        tops = {PurePosixPath(name).parts[0] for name in names}
        if len(tops) != 1:
            raise RegistryError(f"{entry['slug']} {entry['version']}: no pyproject.toml at the archive's root")
        prefix = next(iter(tops)) + "/"
    pyproject = tomllib.loads(archive.read(prefix + "pyproject.toml").decode("utf-8"))
    project, smarter = pyproject.get("project", {}), pyproject.get("tool", {}).get("smarter", {})
    if smarter.get("slug") != entry["slug"] or str(project.get("version")) != entry["version"]:
        raise RegistryError(
            f"{entry['slug']} {entry['version']}: the archive is {smarter.get('slug')} {project.get('version')}"
        )
    package = smarter.get("package", "")
    try:
        source = archive.read(f"{prefix}{package}/__init__.py").decode("utf-8")
    except KeyError as e:
        raise RegistryError(f"{entry['slug']} {entry['version']}: the archive has no {package}/__init__.py") from e
    return Archive(project=project, smarter=smarter, docstring=ast.get_docstring(ast.parse(source)) or "")
