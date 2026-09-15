"""Skill linking: symlink -> junction -> copy abstraction.

skills/ in the workspace is the single source of truth; agent tools see the
skills through links created here. Nothing outside this module needs to know
which link flavor is in use.

Guarantees:
  - idempotent: re-running link on a healthy link is a no-op
  - foreign directories (real dirs we did not create) are backed up to
    backups/ and never silently deleted
  - copy-mode targets carry a .agentctl-copy marker with the source content
    hash, so staleness is detected and re-synced
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat as stat_mod
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentctl.utils import backup_path, shasum

COPY_MARKER = ".agentctl-copy"
STRATEGIES = ("auto", "symlink", "junction", "copy")

HEALTHY = "healthy"
MISSING = "missing"
WRONG_TARGET = "wrong-target"
FOREIGN = "foreign"
STALE = "stale"
NO_SOURCE = "no-source"


class LinkError(RuntimeError):
    pass


# --------------------------------------------------------------- detection

def is_junction(p: Path) -> bool:
    if os.name != "nt":
        return False
    if p.is_symlink():
        return False
    if hasattr(os.path, "isjunction"):  # Python 3.12+
        return os.path.isjunction(os.fspath(p))
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return getattr(st, "st_reparse_tag", 0) == stat_mod.IO_REPARSE_TAG_MOUNT_POINT


def is_link(p: Path) -> bool:
    return p.is_symlink() or is_junction(p)


def _norm(path: Path | str) -> str:
    s = str(path)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    return os.path.normcase(os.path.normpath(s))


def link_target(p: Path) -> Path | None:
    try:
        return Path(os.readlink(p))
    except (OSError, ValueError):
        return None


def dir_hash(d: Path) -> str:
    """Stable content hash of a directory (detects copy staleness)."""
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name == COPY_MARKER:
            continue
        h.update(p.relative_to(d).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(shasum(p).encode("ascii"))
    return h.hexdigest()


# ------------------------------------------------------------------- state

def link_state(source: Path, target: Path) -> str:
    if target.is_symlink() or is_junction(target):
        t = link_target(target)
        if t is not None and _norm(t) == _norm(source):
            return HEALTHY
        return WRONG_TARGET
    if target.is_dir():
        marker = target / COPY_MARKER
        if marker.is_file():
            try:
                prev = marker.read_text(encoding="utf-8").strip()
            except OSError:
                prev = ""
            return HEALTHY if prev == dir_hash(source) else STALE
        return FOREIGN
    if target.exists():
        return FOREIGN
    return MISSING


# ---------------------------------------------------------------- creation

def _mk_junction(source: Path, target: Path) -> None:
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", os.fspath(target), os.fspath(source)],
        capture_output=True,
    )
    if proc.returncode != 0 or not target.exists():
        raise LinkError(f"mklink /J failed for {target}")


def create_link(source: Path, target: Path, strategy: str = "auto") -> str:
    """Create `target` pointing at `source`. Returns the method used."""
    if not source.is_dir():
        raise LinkError(f"Skill source directory does not exist: {source}")
    if strategy not in STRATEGIES:
        raise LinkError(f"Unknown link strategy '{strategy}' (use: {', '.join(STRATEGIES)})")
    if strategy == "auto":
        chain = ["symlink", "junction", "copy"] if os.name == "nt" else ["symlink", "copy"]
    else:
        chain = [strategy]

    target.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for method in chain:
        try:
            if method == "symlink":
                os.symlink(source, target, target_is_directory=True)
                return "symlink"
            if method == "junction":
                _mk_junction(source, target)
                return "junction"
            shutil.copytree(source, target, dirs_exist_ok=True)
            (target / COPY_MARKER).write_text(dir_hash(source) + "\n", encoding="utf-8")
            return "copy"
        except (OSError, LinkError) as e:
            last_err = e
            # clean partial attempts before trying the next method
            if is_link(target):
                remove_link(target)
            elif target.is_dir() and (target / COPY_MARKER).is_file():
                shutil.rmtree(target, ignore_errors=True)
            continue
    raise LinkError(f"Could not link {target} -> {source}: {last_err}")


def remove_link(p: Path) -> None:
    """Remove a symlink/junction without touching what it points to."""
    try:
        os.unlink(p)
    except OSError:
        os.rmdir(p)


def remove_managed(target: Path) -> None:
    """Remove something this tool created (link or marked copy). Never foreign."""
    if is_link(target):
        remove_link(target)
    elif target.is_dir() and (target / COPY_MARKER).is_file():
        shutil.rmtree(target)
    else:
        raise LinkError(f"Refusing to remove unmanaged path: {target}")


# --------------------------------------------------------------- manager

def resolve_target(root: Path, target: str) -> Path:
    p = Path(target).expanduser()
    if not p.is_absolute():
        p = root / p
    return p


@dataclass
class LinkAction:
    skill: str
    source: Path
    target: Path
    state: str
    action: str  # none | create | replace | backup-replace | sync | skip


class LinkManager:
    def __init__(self, root: Path, strategy: str = "auto", targets: list[Path] | None = None):
        self.root = root
        self.strategy = strategy
        self.targets = targets or []
        self.backup_root = root / "backups"

    @classmethod
    def from_config(cls, root: Path, cfg) -> "LinkManager":
        links = cfg.links
        strategy = str(links.get("strategy", "auto"))
        targets = [resolve_target(root, str(t)) for t in (links.get("targets") or [])]
        return cls(root, strategy, targets)

    def plan(self, skills: list[str]) -> list[LinkAction]:
        """Each skill is linked at `<target>/<skill>` inside every target dir."""
        actions: list[LinkAction] = []
        for skill in skills:
            source = self.root / "skills" / skill
            for t in self.targets:
                link_at = t / skill
                if not source.is_dir():
                    actions.append(LinkAction(skill, source, link_at, NO_SOURCE, "skip"))
                    continue
                state = link_state(source, link_at)
                act = {
                    HEALTHY: "none",
                    MISSING: "create",
                    WRONG_TARGET: "replace",
                    FOREIGN: "backup-replace",
                    STALE: "sync",
                }[state]
                actions.append(LinkAction(skill, source, link_at, state, act))
        return actions

    def apply(self, actions: list[LinkAction], dry_run: bool = False) -> list[str]:
        log: list[str] = []
        for a in actions:
            if a.action == "skip":
                log.append(f"WARN skill '{a.skill}' has no source directory: {a.source}")
                continue
            if a.action == "none":
                continue
            if dry_run:
                log.append(f"[dry-run] {a.action}: {a.skill} -> {a.target}")
                continue
            if a.action == "backup-replace":
                bak = backup_path(a.target, self.backup_root)
                log.append(f"backed up foreign directory {a.target} -> {bak}")
            elif a.action == "replace":
                remove_link(a.target)
            elif a.action == "sync":
                shutil.rmtree(a.target, ignore_errors=True)
            method = create_link(a.source, a.target, self.strategy)
            log.append(f"linked {a.skill} -> {a.target} ({method})")
        return log

    def status(self, skills: list[str]) -> tuple[int, int, list[str]]:
        """(healthy, total, problems). Sources without a skill dir are skipped
        here -- doctor reports them separately."""
        healthy, total, problems = 0, 0, []
        for a in self.plan(skills):
            if a.state == NO_SOURCE:
                continue
            total += 1
            if a.state == HEALTHY:
                healthy += 1
            else:
                problems.append(f"{a.skill} @ {a.target}: {a.state}")
        return healthy, total, problems

    def unlink(self, skills: list[str], dry_run: bool = False) -> list[str]:
        log: list[str] = []
        for skill in skills:
            source = self.root / "skills" / skill
            for t in self.targets:
                link_at = t / skill
                state = link_state(source, link_at)
                if state in (HEALTHY, WRONG_TARGET, STALE):
                    if dry_run:
                        log.append(f"[dry-run] unlink {skill} @ {link_at}")
                        continue
                    remove_managed(link_at)
                    log.append(f"unlinked {skill} @ {link_at}")
                elif state == FOREIGN:
                    log.append(f"WARN refusing to touch unmanaged directory {link_at}")
        return log