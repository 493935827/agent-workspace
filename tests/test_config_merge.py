"""Config merge semantics: union lists, recursive dicts, replaced targets."""
import pytest

from agentctl.config import ConfigError, build_effective, merge


def test_lists_union_preserves_order():
    assert merge(["a", "b"], ["b", "c"], _key="skills") == ["a", "b", "c"]


def test_dicts_merge_recursively():
    assert merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}}) == \
        {"a": {"x": 1, "y": 3, "z": 4}}


def test_scalar_override():
    assert merge("auto", "junction") == "junction"


def test_targets_replaced_not_unioned():
    base = {"links": {"targets": ["/a"], "strategy": "auto"}}
    over = {"links": {"targets": ["/b"]}}
    merged = merge(base, over)
    assert merged["links"]["targets"] == ["/b"]
    assert merged["links"]["strategy"] == "auto"


def test_effective_skills_union_and_exclude(ws):
    cfg = build_effective(ws, "personal")
    assert cfg.enabled_skills == ["alpha", "beta", "gamma"]

    cfg = build_effective(ws, "company")
    # common: alpha, beta; company excludes beta and adds nothing
    assert cfg.enabled_skills == ["alpha"]


def test_local_layer_overrides_and_extends(ws):
    (ws / "local.yaml").write_text(
        "environment: company\n"
        "skills:\n  - gamma\n"
        "links:\n  targets:\n    - /tmp/other\n",
        encoding="utf-8",
    )
    cfg = build_effective(ws, "company")
    assert "gamma" in cfg.enabled_skills
    assert cfg.links["targets"] == ["/tmp/other"]  # replaced, not unioned
    assert "local.yaml" in cfg.sources
    assert "environment" not in cfg.raw.get("skills", [])  # marker stripped


def test_unknown_profile_raises(ws):
    with pytest.raises(ConfigError):
        build_effective(ws, "nonexistent")


def test_internet_default_true_and_intranet_false(ws):
    assert build_effective(ws, "personal").internet is True
    (ws / "configs" / "intranet.yaml").write_text(
        "network:\n  internet: false\n", encoding="utf-8")
    assert build_effective(ws, "intranet").internet is False