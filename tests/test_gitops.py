"""gitops hardening: bounded subprocesses, no stdin, no leaked credentials.

Review item: git calls had no timeout and could inherit stdin (hang on a
credential prompt), and GitError messages passed git's stderr through
verbatim -- including URLs with embedded user:token credentials.
"""
from __future__ import annotations

import subprocess

import pytest

from agentctl import gitops


# ----------------------------------------------------------------- redact

@pytest.mark.parametrize("raw, expected", [
    ("https://user:token@example.com/org/repo.git",
     "https://***@example.com/org/repo.git"),
    ("ssh://deploy-key@server.example.com/srv/git/repo.git",
     "ssh://***@server.example.com/srv/git/repo.git"),
    ("fatal: unable to access 'https://ci-bot:p4ss@host/x/y/': 403",
     "fatal: unable to access 'https://***@host/x/y/': 403"),
    # no userinfo -> untouched
    ("https://example.com/org/repo.git", "https://example.com/org/repo.git"),
    # scp-like syntax and bare emails are not URLs with a scheme; left alone
    ("git@github.com:org/repo.git", "git@github.com:org/repo.git"),
    ("maintainer@example.com", "maintainer@example.com"),
    ("", ""),
])
def test_redact_masks_url_userinfo(raw, expected):
    assert gitops.redact(raw) == expected


# ------------------------------------------------------- subprocess policy

class _RunSpy:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls: list[dict] = []
        self._result = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr)

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_git_runs_without_stdin_and_with_timeout(tmp_path, monkeypatch):
    spy = _RunSpy(stdout="ok\n")
    monkeypatch.setattr(gitops.subprocess, "run", spy)

    gitops.short_commit(tmp_path)

    kwargs = spy.calls[0]["kwargs"]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["timeout"] == gitops.DEFAULT_TIMEOUT
    assert kwargs["capture_output"] is True


def test_timeout_raises_git_error(tmp_path, monkeypatch):
    spy = _RunSpy()
    spy._result = subprocess.TimeoutExpired(cmd=["git"], timeout=gitops.DEFAULT_TIMEOUT)
    monkeypatch.setattr(gitops.subprocess, "run", spy)

    with pytest.raises(gitops.GitError, match="timed out"):
        gitops.fetch(tmp_path)


def test_git_error_message_masks_embedded_credentials(tmp_path, monkeypatch):
    secret = "s3cr3t-token-value"
    stderr = (f"fatal: unable to access 'https://ci-bot:{secret}@example.com/x/y/': "
              "The requested URL returned error: 403")
    spy = _RunSpy(returncode=128, stderr=stderr)
    monkeypatch.setattr(gitops.subprocess, "run", spy)

    with pytest.raises(gitops.GitError) as exc:
        gitops.fetch(tmp_path)

    message = str(exc.value)
    assert secret not in message
    assert "https://***@example.com/x/y/" in message
