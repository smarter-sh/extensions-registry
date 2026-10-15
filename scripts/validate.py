"""
Validate the registry: publishers, entries, slug ownership, and the archives of new or changed entries.

On a pull request, entries that already exist on the base branch may not change, and the archives
of new entries are downloaded and checked. Run with ``--all`` to check every archive.
"""

import argparse
import subprocess  # nosec B404
import sys

from registry import (
    ROOT,
    RegistryError,
    check_slug_ownership,
    download,
    entry_paths,
    load_entry,
    load_publishers,
    read_archive,
)


def changed_entries(base: str) -> tuple[set[str], set[str]]:
    """Return the entries that a pull request adds, and those it modifies or deletes, relative to ``base``."""
    output = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--name-status", f"{base}...HEAD", "--", "extensions"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    added, changed = set(), set()
    for line in output.splitlines():
        status, *paths = line.split("\t")
        (added if status == "A" else changed).add(paths[-1])
    return added, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="The pull request's base, e.g. origin/main.")
    parser.add_argument("--all", action="store_true", help="Download and check every entry's archive.")
    args = parser.parse_args()
    errors = []
    try:
        publishers = load_publishers()
        entries = {str(path.relative_to(ROOT)): load_entry(path, publishers) for path in entry_paths()}
        check_slug_ownership(list(entries.values()))
    except RegistryError as e:
        print(f"error: {e}")
        return 1
    to_check = set(entries) if args.all else set()
    if args.base:
        added, changed = changed_entries(args.base)
        errors += [f"{path}: a released version may not be changed or deleted" for path in sorted(changed)]
        to_check |= added
    for path in sorted(to_check):
        entry = entries[path]
        try:
            archive = read_archive(entry, download(entry["archive_url"]))
            print(f"ok: {entry['slug']} {entry['version']} ({archive.project.get('name')})")
        except (RegistryError, OSError) as e:
            errors.append(f"{path}: {e}")
    for error in errors:
        print(f"error: {error}")
    print(f"{len(entries)} entries, {len(publishers)} publishers, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
