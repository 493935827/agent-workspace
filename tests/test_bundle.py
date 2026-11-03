"""Offline bundle: exclusion rules, verification, roundtrip import, safety."""
import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from agentctl import gitops
from agentctl.bundle import (BundleError, collect_files, export_bundle,
                             import_bundle, read_manifest_and_verify)


def test_export_excludes_local_state_and_env(ws, tmp_path):
    (ws / ".env").write_text("TOKEN_A=supersecret\n", encoding="utf-8")
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")

    out = export_bundle(ws, output=tmp_path / "b.zip")

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert not any(n.endswith("/.env") or n == ".env" for n in names)
    assert not any("local.yaml" in n for n in names)

    manifest = read_manifest_and_verify(out)
    assert manifest["version"] == "0.1.0"
    assert "alpha" in manifest["skills"]
    assert (ws / "manifests").is_dir()  # audit copy kept locally


def test_roundtrip_import_restores_files_and_keeps_local_state(ws, tmp_path):
    (ws / "skills" / "alpha" / "SKILL.md").write_text("alpha v2\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")

    # the "intranet machine" drifted to an older file
    (ws / "skills" / "alpha" / "SKILL.md").write_text("alpha v1\n", encoding="utf-8")
    # machine-local state that must survive an import untouched
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")
    (ws / ".env").write_text("TOKEN_A=zzz\n", encoding="utf-8")

    rc = import_bundle(ws, out)

    assert rc == 0
    assert (ws / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "alpha v2\n"
    assert (ws / "local.yaml").read_text(encoding="utf-8") == "environment: personal\n"
    assert (ws / ".env").read_text(encoding="utf-8") == "TOKEN_A=zzz\n"
    assert list((ws / "backups").glob("workspace-v*.zip")), "import must back up first"


def test_tampered_bundle_rejected(ws, tmp_path):
    out = export_bundle(ws, output=tmp_path / "b.zip")

    src = tmp_path / "rezip"
    with zipfile.ZipFile(out) as zf:
        zf.extractall(src)
    (src / "workspace" / "skills" / "alpha" / "SKILL.md").write_text("tampered\n",
                                                                     encoding="utf-8")
    out2 = tmp_path / "b2.zip"
    with zipfile.ZipFile(out2, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src).as_posix())

    with pytest.raises(BundleError, match="checksum"):
        read_manifest_and_verify(out2)


def test_downgrade_requires_force(ws, tmp_path):
    (ws / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # bundle v2.0.0
    (ws / "VERSION").write_text("2.1.0\n", encoding="utf-8")  # workspace now newer

    rc = import_bundle(ws, out)
    assert rc == 1
    assert (ws / "VERSION").read_text(encoding="utf-8") == "2.1.0\n"


def test_secret_scan_blocks_export(ws, tmp_path):
    (ws / "skills" / "alpha" / "notes.md").write_text(
        "my key: sk-abcdefghijklmnopqrstuvwx\n", encoding="utf-8")  # agentctl-canary
    with pytest.raises(BundleError, match="notes.md"):
        export_bundle(ws, output=tmp_path / "b.zip")


def test_secret_scan_allows_marked_canary_lines(ws, tmp_path):
    (ws / "skills" / "alpha" / "canary.md").write_text(
        "sample: sk-abcdefghijklmnopqrstuvwx  # agentctl-canary\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # must not raise
    assert out.exists()


def test_secret_scan_ignores_hyphenated_url_slugs(ws, tmp_path):
    # regression: Microsoft Learn URLs in ui-ux-pro-max stack CSVs end in
    # 'task-based-asynchronous-programming', whose 'sk-based-...' substring
    # used to trip the OpenAI-key pattern and block export
    (ws / "skills" / "alpha" / "winui.csv").write_text(
        "28,Threading,Use Task.Run for CPU-bound work,High,"
        "https://learn.microsoft.com/en-us/dotnet/standard/parallel-programming/"
        "task-based-asynchronous-programming,active,2026-08-13\n",
        encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # must not raise
    assert out.exists()


def test_secret_scan_blocks_prefixed_api_keys(ws, tmp_path):
    for i, key in enumerate((
        "sk-proj-q1w2e3r4t5y6u7i8o9p0z1x2",       # agentctl-canary
        "sk-ant-api03-q1w2e3r4t5y6u7i8o9p0z1x2",  # agentctl-canary
        "sk-or-v1-q1w2e3r4t5y6u7i8o9p0z1x2",      # agentctl-canary
    )):
        (ws / "skills" / "alpha" / f"key{i}.md").write_text(
            f"token: {key}\n", encoding="utf-8")
    with pytest.raises(BundleError, match=r"(?s)key0\.md.*key1\.md.*key2\.md"):
        export_bundle(ws, output=tmp_path / "b.zip")


def test_export_dry_run_writes_nothing(ws, tmp_path):
    out = tmp_path / "b.zip"
    export_bundle(ws, output=out, dry_run=True)
    assert not out.exists()
    assert not (ws / "dist").exists() or not any((ws / "dist").iterdir())


def test_export_excludes_reverse_engineering_project(ws, tmp_path):
    # CloudMusic_R / orpheus 逆向工作区整体在包范围之外：既不入包，
    # 密钥扫描也不应再扫到其 vendor JS chunk（真实误报场景，无 canary 标记）
    chunk = (ws / "projects" / "cloudmusic-r" / "orpheus" / "pub" / "hybrid"
             / "89.chunk.83304b1.js")
    chunk.parent.mkdir(parents=True)
    chunk.write_text("var k='-----BEGIN RSA PRIVATE KEY-----';\n", encoding="utf-8")  # agentctl-canary
    (ws / "projects" / "cloudmusic-r" / "README.md").write_text(
        "analysis notes\n", encoding="utf-8")

    out = export_bundle(ws, output=tmp_path / "b.zip")  # must not raise

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert not any(n.startswith("workspace/projects/") for n in names)
    assert any(n.startswith("workspace/skills/") for n in names)


def test_import_refuses_bundle_entries_under_excluded_prefix(ws, tmp_path):
    # 排除前缀对 import 同样生效：包内出现该前缀条目时拒绝而非覆盖本地副本
    # （重新签名 SHA256SUMS 越过恒等校验，专测前缀防御本身）
    out = export_bundle(ws, output=tmp_path / "b.zip")
    src = tmp_path / "rezip"
    with zipfile.ZipFile(out) as zf:
        zf.extractall(src)
    rogue = src / "workspace" / "projects" / "cloudmusic-r" / "x.js"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("payload\n", encoding="utf-8")
    _rewrite_sums(src)
    out2 = _rezip(src, tmp_path / "b2.zip")

    with pytest.raises(BundleError, match="projects/cloudmusic-r"):
        import_bundle(ws, out2)


# --------------------------------------------------------------- helpers

def _extract_to(bundle: Path, src: Path) -> None:
    with zipfile.ZipFile(bundle) as zf:
        zf.extractall(src)


def _rezip(src: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src).as_posix())
    return dest


def _rewrite_sums(src: Path) -> None:
    """Recompute SHA256SUMS over the whole extracted tree, simulating an
    attacker who re-signs the manifest wholesale."""
    lines = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            rel = p.relative_to(src).as_posix()
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}\n")
    (src / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


# ------------------------------------------------------------- deny lists

def test_export_walk_mode_excludes_personal_and_heavy_paths(ws, tmp_path):
    # walk 模式（内网机无 git 时的常态）同样必须挡住个人数据、团队状态与
    # 大型归档：user-data / work / .agent-teams / .uv-cache / projects/xerj / *.7z
    (ws / "user-data" / "copyq").mkdir(parents=True)
    (ws / "user-data" / "copyq" / "copyq_tab_a.dat").write_bytes(b"\x00clipboard")
    (ws / "work").mkdir()
    (ws / "work" / "scratch.md").write_text("internal notes\n", encoding="utf-8")
    (ws / ".agent-teams").mkdir()
    (ws / ".agent-teams" / "team.json").write_text("{}", encoding="utf-8")
    (ws / ".uv-cache").mkdir()
    (ws / ".uv-cache" / "cached").write_text("x", encoding="utf-8")
    (ws / "projects" / "xerj" / "upstream.c").parent.mkdir(parents=True)
    (ws / "projects" / "xerj" / "upstream.c").write_text("int main(){}\n", encoding="utf-8")
    (ws / "skills" / "serial-debug.7z").write_bytes(b"7z\xbc\xaf\x27\x1c")

    out = export_bundle(ws, output=tmp_path / "b.zip")

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    for prefix in ("workspace/user-data/", "workspace/work/",
                   "workspace/.agent-teams/", "workspace/.uv-cache/",
                   "workspace/projects/"):
        assert not any(n.startswith(prefix) for n in names), prefix
    assert not any(n.endswith(".7z") for n in names)
    assert any(n == "workspace/skills/alpha/SKILL.md" for n in names)


@pytest.mark.skipif(not gitops.available(), reason="git not on PATH")
def test_collect_git_mode_applies_deny_lists(ws, tmp_path):
    # git 模式（含被强制 add 的 gitignored 路径）与 walk 模式共用同一套
    # DENY 清单，两边都必须生效
    (ws / "user-data" / "copyq").mkdir(parents=True)
    (ws / "user-data" / "copyq" / "copyq.ini").write_text("[Options]\n", encoding="utf-8")
    (ws / "work").mkdir()
    (ws / "work" / "notes.md").write_text("internal notes\n", encoding="utf-8")
    (ws / "skills" / "alpha" / "tool.7z").write_bytes(b"PK\x03\x04")
    (ws / "projects" / "xerj" / "upstream.c").parent.mkdir(parents=True)
    (ws / "projects" / "xerj" / "upstream.c").write_text("int main(){}\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(ws), "-c", "user.email=test@example.com",
             "-c", "user.name=test", "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True)

    git("init")
    git("add", "-A")
    git("commit", "-m", "init", "--quiet")

    files, mode = collect_files(ws)

    assert mode == "git"
    rels = [f.relative_to(ws).as_posix() for f in files]
    assert not any(r.startswith("user-data/") for r in rels)
    assert not any(r.startswith("work/") for r in rels)
    assert not any(r.endswith(".7z") for r in rels)
    assert not any(r.startswith("projects/xerj/") for r in rels)
    assert "configs/common.yaml" in rels


def test_walk_collection_skips_symlinked_directories(ws, tmp_path):
    # Python <= 3.12 的 rglob 会跟随目录 symlink 走出工作区；收集必须
    # 停在树内，不得把外部文件收进离线包
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
    link = ws / "skills" / "alpha" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform")

    files, mode = collect_files(ws)

    assert mode == "walk"
    assert all("escape" not in f.relative_to(ws).as_posix() for f in files)
    out = export_bundle(ws, output=tmp_path / "b.zip")
    with zipfile.ZipFile(out) as zf:
        assert not any("escape" in n for n in zf.namelist())


# -------------------------------------------------- sums identity (import)

def test_import_rejects_unlisted_bundle_entries(ws, tmp_path):
    # 夹带注入：包内多出未列入 SHA256SUMS 的文件必须被拒，否则可绕过校验
    out = export_bundle(ws, output=tmp_path / "b.zip")
    src = tmp_path / "rezip"
    _extract_to(out, src)
    rogue = src / "workspace" / "skills" / "alpha" / "rogue.js"
    rogue.write_text("payload\n", encoding="utf-8")
    out2 = _rezip(src, tmp_path / "b2.zip")

    with pytest.raises(BundleError, match="SHA256SUMS does not cover"):
        read_manifest_and_verify(out2)


def test_import_rejects_missing_sums_entries(ws, tmp_path):
    # 反向恒等：SHA256SUMS 列出但包内缺失的条目同样必须被拒
    out = export_bundle(ws, output=tmp_path / "b.zip")
    src = tmp_path / "rezip"
    _extract_to(out, src)
    (src / "workspace" / "VERSION").unlink()
    out2 = _rezip(src, tmp_path / "b2.zip")

    with pytest.raises(BundleError, match="lists missing entry"):
        read_manifest_and_verify(out2)


def test_import_refuses_entries_in_denied_dirs(ws, tmp_path):
    # 防御纵深：即使 sums 被整体重签（恒等校验通过），import 也不得写入
    # 排除目录（如 .git/）
    out = export_bundle(ws, output=tmp_path / "b.zip")
    src = tmp_path / "rezip"
    _extract_to(out, src)
    rogue = src / "workspace" / ".git" / "config"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("[core]\n", encoding="utf-8")
    _rewrite_sums(src)
    out2 = _rezip(src, tmp_path / "b2.zip")

    manifest = read_manifest_and_verify(out2)  # sums 恒等校验此时通过
    assert manifest["version"] == "0.1.0"
    assert not (ws / ".git").exists()
    with pytest.raises(BundleError, match=r"\.git"):
        import_bundle(ws, out2)
    assert not (ws / ".git").exists()


# ------------------------------------------------------------- secret scan

def test_secret_scan_covers_large_files(ws, tmp_path):
    # >1MB 的文件不再被静默跳过：其中出现疑似密钥同样拦截导出
    payload = "x" * (1024 * 1024 + 64) + "\nmy key: sk-abcdefghijklmnopqrstuvwx\n"  # agentctl-canary
    (ws / "skills" / "alpha" / "big.txt").write_text(payload, encoding="utf-8")
    with pytest.raises(BundleError, match="big.txt"):
        export_bundle(ws, output=tmp_path / "b.zip")


def test_canary_marker_does_not_exempt_other_secrets(ws, tmp_path):
    # canary 标记只豁免已知假样本自身；真实密钥不能靠在行尾补标记绕过
    key = "sk-" + "RealSecretNotExempt0123456789"
    (ws / "skills" / "alpha" / "leak.md").write_text(
        f"token: {key}  # agentctl-canary\n", encoding="utf-8")
    with pytest.raises(BundleError, match="leak.md"):
        export_bundle(ws, output=tmp_path / "b.zip")