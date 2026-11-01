"""hermes-gruvbox — install, retire and remove the pack's Gruvbox skins.

Stdlib only, no network, no imports of Hermes internals at import time. `__init__.py`
calls `install()` when the plugin loads.

The skins are the pack's source data: each file in `skins/` is a complete Hermes
skin, and installing copies them into `<hermes home>/skins/`. A skin the user
edited, or a same-named file the pack did not write, is never touched. The pack
registers no commands and never switches the active skin.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path

PACKAGE = "hermes-gruvbox"
VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
SKINS = ROOT / "skins"


class ThemeError(RuntimeError):
    """Anything the user can fix: unknown theme, missing file, bad home."""


# ── helpers ───────────────────────────────────────────────────────────────────


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    """Write `path` via a same-directory temp file, so a reader never sees a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".hermes-gruvbox-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def catalog() -> list[dict]:
    """The pack, as shipped (skins/index.json)."""
    return json.loads((SKINS / "index.json").read_text(encoding="utf-8"))


def default_home() -> Path:
    """The active Hermes home, profile-aware when Hermes is importable."""
    try:
        from hermes_constants import get_hermes_home
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return Path(get_hermes_home())


def resolve_home(home) -> Path:
    return Path(home if home is not None else default_home()).expanduser().resolve()


def guarded(home: Path, path: Path) -> Path:
    """Refuse a target that is a symlink or points outside the chosen home."""
    if path.is_symlink() or not path.resolve().is_relative_to(home):
        raise ThemeError(f"refusing symlink or escaped target: {path}")
    return path


def receipt_path(home: Path) -> Path:
    return guarded(home, home / "theme-packages" / f"{PACKAGE}.json")


def load_receipt(home: Path) -> dict:
    path = receipt_path(home)
    if not path.exists():
        return {"version": VERSION, "disabled": False, "skins": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": VERSION, "disabled": False, "skins": {}}
    state.setdefault("version", VERSION)
    state.setdefault("disabled", False)
    state.setdefault("skins", {})
    return state


def save_receipt(home: Path, state: dict) -> None:
    path = receipt_path(home)
    if state["skins"] or state["disabled"]:
        atomic_write(path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
    elif path.exists():
        path.unlink()


# ── install / uninstall ───────────────────────────────────────────────────────


def retire(home: Path, state: dict) -> list[str]:
    """Drop receipt entries for skins this version no longer ships (a rename).

    Returns the names whose files were removed or restored. A file that is missing
    or no longer byte-for-byte ours is left alone and merely forgotten — the pack
    never deletes work it did not write.
    """
    shipped = {entry["skin"] for entry in catalog()}
    retired: list[str] = []
    for name in sorted(state["skins"]):
        if name in shipped:
            continue
        record = state["skins"].pop(name)
        try:
            target = guarded(home, home / "skins" / f"{name}.yaml")
        except ThemeError:
            continue  # never build a path from an unexpected receipt key
        if not target.exists() or digest(target.read_bytes()) != record.get("sha256"):
            continue
        previous = record.get("previous")
        if previous is None:
            target.unlink()
        else:
            atomic_write(target, base64.b64decode(previous, validate=True))
        retired.append(name)
    return retired


def install(home=None, names=None, replace: bool = False) -> tuple[list[str], list[str]]:
    """Copy the pack's skins into `<home>/skins/`. Returns (changed, skipped).

    A skin whose file was edited or deleted after we installed it is the user's
    now and is never overwritten, unless `replace=True` — which backs the old
    bytes up first and restores them on uninstall.
    """
    home = resolve_home(home)
    state = load_receipt(home)
    if state["disabled"]:
        return [], [entry["skin"] for entry in catalog()]

    retire(home, state)  # drop skins an earlier version shipped under another name
    wanted = [entry["skin"] for entry in catalog()] if names is None else list(names)
    changed, skipped = [], []
    for name in wanted:
        source = SKINS / f"{name}.yaml"
        if not source.is_file():
            raise ThemeError(f"pack file missing: {source}")
        data = source.read_bytes()
        target = guarded(home, home / "skins" / f"{name}.yaml")
        record = state["skins"].get(name)
        current = target.read_bytes() if target.exists() else None

        if record is not None:
            if current is None or digest(current) != record["sha256"]:
                skipped.append(name)  # removed or edited by the user: theirs now
                continue
        elif current is not None:
            if not replace:
                skipped.append(name)  # the user's own skin under the same name
                continue
            record = {"previous": base64.b64encode(current).decode()}
        else:
            record = {"previous": None}

        state["skins"][name] = {**record, "sha256": digest(data)}
        save_receipt(home, state)  # receipt first: an interruption fails closed
        if current == data:
            continue
        atomic_write(target, data)
        changed.append(name)
    save_receipt(home, state)
    return changed, skipped


def uninstall(home=None) -> tuple[list[str], list[str]]:
    """Remove the pack's skins that are still byte-for-byte ours. Returns (removed, kept)."""
    home = resolve_home(home)
    state = load_receipt(home)
    removed, kept = [], []
    known = {entry["skin"] for entry in catalog()}
    for name in sorted(state["skins"]):
        record = state["skins"][name]
        if name not in known:
            del state["skins"][name]  # never build a path from an unknown receipt key
            continue
        target = guarded(home, home / "skins" / f"{name}.yaml")
        if not target.exists() or digest(target.read_bytes()) != record["sha256"]:
            kept.append(name)
            continue
        if record["previous"] is None:
            target.unlink()
        else:
            atomic_write(target, base64.b64decode(record["previous"], validate=True))
        removed.append(name)
    for name in removed:
        del state["skins"][name]
    state["disabled"] = True
    save_receipt(home, state)
    return removed, kept


def installed(home=None) -> list[str]:
    """Pack skins currently present on disk, in shipped order."""
    home = resolve_home(home)
    return [entry["skin"] for entry in catalog()
            if (home / "skins" / f"{entry['skin']}.yaml").is_file()]


def set_disabled(home, disabled: bool) -> None:
    """Flip the receipt's `disabled` flag — the switch `install()` honours."""
    home = resolve_home(home)
    state = load_receipt(home)
    state["disabled"] = bool(disabled)
    save_receipt(home, state)
