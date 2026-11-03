"""update: after pull, re-linking must use the freshly rebuilt config.

Regression for review R3 (H3): cli.py built the effective config *before* the
pull, and run_update re-linked with that stale cfg, so a newly enabled skill
needed a manual `agentctl link`. git is faked via monkeypatch; the pull side
effect edits the tmp workspace's configs, never the network or real repos.
"""
from __future__ import annotations

import pytest

from agentctl import gitops
from agentctl.config import build_effective
from agentctl.links import resolve_target
from agentctl.update import run_update

COMMIT_OLD = "1" * 40
COMMIT_NEW = "2" * 40


def target_dir(ws):
    cfg = build_effective(ws, "personal")
    return resolve_target(ws, str(cfg.links["targets"][0]))


def enable_skill_on_pull(ws, skill: str):
    """Simulate upstream delivering a config change that enables `skill`."""
    profile = ws / "configs" / "personal.yaml"
    profile.write_text(profile.read_text(encoding="utf-8") + f"  - {skill}\n",
                       encoding="utf-8")


def add_skill_dir(ws, name: str) -> None:
    (ws / "skills" / name).mkdir()
    (ws / "skills" / name / "SKILL.md").write_text(
        f"---\nname: {name}\n---\n# {name}\n", encoding="utf-8")


@pytest.fixture
def fake_git(monkeypatch):
    """Stand-in for every gitops call run_update makes. All writes go through
    monkeypatch so nothing leaks between tests."""
    calls = {"fetch": 0, "pull": 0}

    def install(pull_side_effect=None, ahead_behind=(0, 1),
                fetch_error: str | None = None, pull_error: str | None = None):
        commits = iter([COMMIT_OLD, COMMIT_NEW])
        monkeypatch.setattr(gitops, "available", lambda: True)
        monkeypatch.setattr(gitops, "is_repo", lambda root: True)
        monkeypatch.setattr(gitops, "has_commits", lambda root: True)
        monkeypatch.setattr(gitops, "upstream", lambda root: "origin/main")

        def do_fetch(root):
            calls["fetch"] += 1
            if fetch_error:
                raise gitops.GitError(fetch_error)

        def do_pull(root):
            calls["pull"] += 1
            if pull_error:
                raise gitops.GitError(pull_error)
            if pull_side_effect:
                pull_side_effect(root)

        monkeypatch.setattr(gitops, "fetch", do_fetch)
        monkeypatch.setattr(gitops, "ahead_behind", lambda root: ahead_behind)
        monkeypatch.setattr(
            gitops, "log_oneline",
            lambda root, rev: ["abc1234 feat: bring a new skill config"])
        monkeypatch.setattr(gitops, "current_commit",
                            lambda root: next(commits, COMMIT_NEW))
        monkeypatch.setattr(gitops, "pull_ff_only", do_pull)
        return calls

    return install


def test_pull_then_relink_uses_new_config(ws, fake_git, capsys):
    add_skill_dir(ws, "delta")
    calls = fake_git(pull_side_effect=lambda root: enable_skill_on_pull(root, "delta"))

    cfg_before = build_effective(ws, "personal")
    assert "delta" not in cfg_before.enabled_skills  # stale by construction

    rc = run_update(ws, cfg_before, "personal")

    assert rc == 0
    assert calls["pull"] == 1
    out = capsys.readouterr().out
    assert "linked delta" in out
    link_at = target_dir(ws) / "delta"
    assert link_at.is_dir()
    assert (link_at / ".agentctl-copy").is_file()  # copy strategy: managed dir
    for name in ("alpha", "beta", "gamma"):  # existing skills stay linked
        assert (target_dir(ws) / name).is_dir()


def test_dry_run_never_pulls_or_links(ws, fake_git, capsys):
    add_skill_dir(ws, "delta")
    calls = fake_git(pull_side_effect=lambda root: enable_skill_on_pull(root, "delta"))

    cfg = build_effective(ws, "personal")
    rc = run_update(ws, cfg, "personal", dry_run=True)

    assert rc == 0
    assert calls["pull"] == 0
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert not (target_dir(ws) / "delta").exists()
    assert "  - delta" not in (ws / "configs" / "personal.yaml").read_text(encoding="utf-8")


def test_offline_environment_refuses_network(ws, fake_git, capsys):
    calls = fake_git()
    cfg = build_effective(ws, "personal")
    cfg.raw["network"] = {"internet": False}

    rc = run_update(ws, cfg, "personal")

    assert rc == 0
    assert calls["fetch"] == 0 and calls["pull"] == 0
    out = capsys.readouterr().out
    assert "offline" in out and "import" in out


def test_pull_failure_reports_and_stops(ws, fake_git, capsys):
    add_skill_dir(ws, "delta")
    calls = fake_git(pull_error="pull failed: non-fast-forward")

    cfg = build_effective(ws, "personal")
    rc = run_update(ws, cfg, "personal")

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert not (target_dir(ws) / "alpha").exists()  # no links touched
    assert "  - delta" not in (ws / "configs" / "personal.yaml").read_text(encoding="utf-8")


def test_fetch_failure_reports_and_stops(ws, fake_git, capsys):
    calls = fake_git(fetch_error="fetch failed: could not resolve host")

    cfg = build_effective(ws, "personal")
    rc = run_update(ws, cfg, "personal")

    assert rc == 1
    assert calls["pull"] == 0
    assert "FAIL" in capsys.readouterr().out
