"""bundle: the tasks and their generators, shipped as one encrypted archive.

    python -m benchmark_ext.bundle unpack    # after cloning: write the tasks and generators into the tree
    python -m benchmark_ext.bundle verify    # check the archive against its recorded checksum
    python -m benchmark_ext.bundle pack      # rebuild the archive from the working tree

Why encrypted, and what that does and does not buy. AppWorld ships its own data the same way, for the same
reason: a benchmark left in plain text on a public host is scraped and ends up in the next model's training
data, and then it no longer measures anything. The password is in this file, so this is a lock against
crawlers, not against a person who wants in. Read the tasks freely; just unpack them yourself.

The archive holds the task worlds (`benchmark_ext/data/tasks/`) and the generators that emitted them
(`benchmark_ext/generate/tasks/task_generators/`, minus `base.py`, which the grader imports at run time).
Generators are in here because they name every planted hazard, which is exactly what must not be crawled.

Each task's `ground_truth/` is stripped on pack to the set AppWorld withholds from its own test split: the
grader, the requirement labels and the answer stay; the reference solution and the call trace go.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(PROJECT, "benchmark_ext", "data", "tasks.bundle")
CHECKSUM = ARCHIVE + ".sha256"

PASSWORD = "appworld-extend-tasks"
SALT = b"appworld-extend-v1"

# What goes in, as paths relative to PROJECT.
SOURCES = (
    os.path.join("benchmark_ext", "data", "tasks"),
    os.path.join("benchmark_ext", "generate", "tasks", "task_generators"),
)
# base.py is imported at run time (store.py, grader.py), so it cannot live inside the archive.
KEEP_OUT_OF_ARCHIVE = ("base.py",)
# The reference solution and its call trace. AppWorld's own "minimal" release mode drops exactly these, and
# its loader is written to work without them.
WITHHELD = ("solution.py", "compiled_solution.py", "generator.py", "api_calls.json",
            "required_apps.json", "required_apis.json")


def _key() -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=SALT, iterations=100_000).derive(
        PASSWORD.encode())


def _encrypt(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, data, None)


def _decrypt(blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(_key()).decrypt(blob[:12], blob[12:], None)


def _archive_members() -> list[tuple[str, str]]:
    """(absolute path, name inside the archive) for everything that ships, skipping caches and withheld files."""
    out: list[tuple[str, str]] = []
    for source in SOURCES:
        for root, dirs, files in os.walk(os.path.join(PROJECT, source)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if name in WITHHELD or name in KEEP_OUT_OF_ARCHIVE or name.endswith(".pyc"):
                    continue
                path = os.path.join(root, name)
                out.append((path, os.path.relpath(path, PROJECT)))
    return sorted(out, key=lambda pair: pair[1])


def pack() -> None:
    members = _archive_members()
    if not members:
        raise SystemExit(f"nothing to pack: no files under {SOURCES}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, name in members:
            zf.write(path, name)
    blob = _encrypt(buffer.getvalue())
    os.makedirs(os.path.dirname(ARCHIVE), exist_ok=True)
    with open(ARCHIVE, "wb") as f:
        f.write(blob)
    digest = hashlib.sha256(blob).hexdigest()
    with open(CHECKSUM, "w") as f:
        f.write(f"{digest}  {os.path.basename(ARCHIVE)}\n")
    print(f"packed {len(members)} files into {os.path.relpath(ARCHIVE, PROJECT)} "
          f"({len(blob) / 1e6:.1f} MB)\nsha256 {digest}")


def verify() -> None:
    if not os.path.isfile(ARCHIVE):
        raise SystemExit(f"missing archive: {ARCHIVE}")
    blob = open(ARCHIVE, "rb").read()
    digest = hashlib.sha256(blob).hexdigest()
    if os.path.isfile(CHECKSUM):
        expected = open(CHECKSUM).read().split()[0]
        if digest != expected:
            raise SystemExit(f"checksum mismatch\n  expected {expected}\n  found    {digest}")
    with zipfile.ZipFile(io.BytesIO(_decrypt(blob))) as zf:
        names = zf.namelist()
    tasks = {n.split("/")[3] for n in names if n.startswith("benchmark_ext/data/tasks/")}
    print(f"ok: {len(names)} files, {len(tasks)} tasks\nsha256 {digest}")


def unpack() -> None:
    if not os.path.isfile(ARCHIVE):
        raise SystemExit(f"missing archive: {ARCHIVE}")
    with zipfile.ZipFile(io.BytesIO(_decrypt(open(ARCHIVE, "rb").read()))) as zf:
        names = zf.namelist()
        zf.extractall(PROJECT)
    tasks = {n.split("/")[3] for n in names if n.startswith("benchmark_ext/data/tasks/")}
    # A stale cache of a generator that is no longer shipped would still be imported by the registry.
    for source in SOURCES:
        for root, dirs, _ in os.walk(os.path.join(PROJECT, source)):
            for d in list(dirs):
                if d == "__pycache__":
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    print(f"unpacked {len(names)} files, {len(tasks)} tasks")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=("pack", "unpack", "verify"))
    {"pack": pack, "unpack": unpack, "verify": verify}[p.parse_args().action]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
