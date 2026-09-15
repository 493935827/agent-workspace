"""Secrets: parsing, SET/MISSING reporting, and zero value leakage."""
from agentctl import secrets as S


def test_parse_env_comments_quotes_and_blank(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# comment\nA=1\nB = \"quoted\"\n\ninvalidline\nC=\nD='single'\n",
        encoding="utf-8",
    )
    assert S.parse_env_file(f) == {"A": "1", "B": "quoted", "C": "", "D": "single"}


def test_check_reports_set_missing_without_values(tmp_path):
    (tmp_path / ".env").write_text("TOKEN_A=supersecretvalue123\n", encoding="utf-8")
    res = S.check(tmp_path, ["TOKEN_A", "TOKEN_B"], [])
    assert res == [("TOKEN_A", True), ("TOKEN_B", False)]
    assert "supersecretvalue123" not in str(res)


def test_check_reads_os_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_A", "x")
    res = S.check(tmp_path, ["TOKEN_A"], [])
    assert res == [("TOKEN_A", True)]


def test_ensure_from_example_never_overwrites(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("A=\n", encoding="utf-8")
    assert S.ensure_from_example(tmp_path) is True
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "A=\n"
    (tmp_path / ".env").write_text("A=real\n", encoding="utf-8")
    assert S.ensure_from_example(tmp_path) is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "A=real\n"