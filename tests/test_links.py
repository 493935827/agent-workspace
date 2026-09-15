"""Link abstraction: creation, fallbacks, idempotency, foreign-dir safety."""
import os

import pytest

from agentctl.links import (FOREIGN, HEALTHY, LinkManager, create_link,
                            is_junction, link_state)


def _make_skill(root):
    src = root / "skills" / "mine"
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text("mine", encoding="utf-8")
    return src


def test_junction_strategy_on_windows(tmp_path):
    if os.name != "nt":
        pytest.skip("junctions are Windows-only")
    root = tmp_path
    src = _make_skill(root)
    tgt = root / "agent-skills" / "mine"
    assert create_link(src, tgt, strategy="junction") == "junction"
    assert is_junction(tgt)
    assert (tgt / "SKILL.md").exists()
    assert link_state(src, tgt) == HEALTHY


def test_copy_strategy_marker_and_resync(tmp_path):
    root = tmp_path
    src = _make_skill(root)
    (src / "a.txt").write_text("1", encoding="utf-8")
    tgt = root / "agent-skills" / "mine"

    assert create_link(src, tgt, strategy="copy") == "copy"
    assert (tgt / ".agentctl-copy").is_file()
    assert link_state(src, tgt) == HEALTHY

    (src / "a.txt").write_text("2", encoding="utf-8")
    assert link_state(src, tgt) == "stale"

    create_link(src, tgt, strategy="copy")  # resync
    assert link_state(src, tgt) == HEALTHY
    assert (tgt / "a.txt").read_text(encoding="utf-8") == "2"


def test_foreign_directory_is_backed_up_not_deleted(tmp_path):
    root = tmp_path
    src = _make_skill(root)
    tgt_dir = root / "agent-skills"
    tgt = tgt_dir / "mine"
    tgt.mkdir(parents=True)
    (tgt / "userfile.txt").write_text("precious", encoding="utf-8")

    assert link_state(src, tgt) == FOREIGN

    lm = LinkManager(root, "copy", [tgt_dir])
    actions = lm.plan(["mine"])
    assert actions[0].action == "backup-replace"
    logs = lm.apply(actions)

    assert any("backed up" in l for l in logs)
    backups = list((root / "backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "userfile.txt").read_text(encoding="utf-8") == "precious"
    assert link_state(src, tgt) == HEALTHY


def test_apply_is_idempotent(tmp_path):
    root = tmp_path
    _make_skill(root)
    tgt_dir = root / "agent-skills"
    lm = LinkManager(root, "copy", [tgt_dir])
    lm.apply(lm.plan(["mine"]))
    again = lm.plan(["mine"])
    assert all(a.action == "none" for a in again)


def test_unlink_removes_only_managed_paths(tmp_path):
    root = tmp_path
    _make_skill(root)
    tgt_dir = root / "agent-skills"
    tgt_dir.mkdir()
    foreign = tgt_dir / "notours"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("keep", encoding="utf-8")

    lm = LinkManager(root, "copy", [tgt_dir])
    lm.apply(lm.plan(["mine"]))
    lm.unlink(["mine"])
    assert not (tgt_dir / "mine").exists()
    assert (foreign / "keep.txt").exists()

    # a foreign directory for a skill we manage is never touched
    (root / "skills" / "other").mkdir()
    (root / "skills" / "other" / "SKILL.md").write_text("o", encoding="utf-8")
    (tgt_dir / "other").mkdir()
    (tgt_dir / "other" / "user.txt").write_text("u", encoding="utf-8")
    logs = lm.unlink(["other"])
    assert (tgt_dir / "other" / "user.txt").exists()
    assert any("refusing" in l for l in logs)