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


# --- explicit merge: null keeps base, structure/scalar conflicts rejected ---


def test_null_override_keeps_base_value():
    assert merge({"a": {"x": 1, "y": 2}}, {"a": None}) == {"a": {"x": 1, "y": 2}}
    assert merge({"a": 1, "b": [1, 2]}, {"a": None, "b": None}) == {"a": 1, "b": [1, 2]}
    assert merge({"x": 1}, None) == {"x": 1}


def test_null_clears_only_resource_version_leaf():
    # Discovery unlock: an explicit null on a resources entry's version leaf
    # is the "declared, unpinned" marker (agentctl/discovery/storage.py
    # adopt writes it) and overrides the inherited pin; anywhere else null
    # keeps the base value (test_null_override_keeps_base_value).
    assert merge(
        {"resources": {"npm": {"a": {"version": "1"}}}},
        {"resources": {"npm": {"a": {"version": None}}}},
    ) == {"resources": {"npm": {"a": {"version": None}}}}
    assert merge(
        {"resources": {"npm": {"a": {"version": "1"}}}},
        {"resources": None},
    ) == {"resources": {"npm": {"a": {"version": "1"}}}}


def test_null_in_profile_keeps_common_value(ws):
    (ws / "configs" / "personal.yaml").write_text(
        "skills: null\nsecrets: null\n", encoding="utf-8")
    cfg = build_effective(ws, "personal")
    assert cfg.skills == ["alpha", "beta"]
    assert cfg.required_secrets == ["TOKEN_A"]
    assert cfg.optional_secrets == ["TOKEN_B"]


def test_null_local_layer_keeps_common_subtree(ws):
    (ws / "local.yaml").write_text("secrets: null\n", encoding="utf-8")
    cfg = build_effective(ws, "personal")
    assert cfg.optional_secrets == ["TOKEN_B"]


def test_structured_scalar_conflict_raises_with_key_path():
    # nested: base dict at a.x met by a scalar
    with pytest.raises(ConfigError, match=r"'a\.x'"):
        merge({"a": {"x": {"y": 1}}}, {"a": {"x": 5}})
    # the "skills: alpha" case: list met by a scalar
    with pytest.raises(ConfigError, match=r"'skills'"):
        merge({"skills": ["alpha"]}, {"skills": "alpha"})
    # nested list met by a scalar, full dotted path in the message
    with pytest.raises(ConfigError, match=r"'secrets\.required'"):
        merge({"secrets": {"required": ["A"]}}, {"secrets": {"required": "A"}})
    # top-level dict met by a scalar
    with pytest.raises(ConfigError, match=r"'links'"):
        merge({"links": {"strategy": "auto"}}, {"links": "copy"})


def test_structured_structured_override_wins_silently():
    # dict <-> list are both structured: higher layer replaces, as before
    assert merge({"a": {"x": 1}}, {"a": [1, 2]}) == {"a": [1, 2]}
    assert merge({"a": [1, 2]}, {"a": {"x": 1}}) == {"a": {"x": 1}}


def test_scalar_mistyped_into_list_key_raises(ws):
    # common defines skills as a list; a profile writing a scalar conflicts
    (ws / "configs" / "personal.yaml").write_text("skills: gamma\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"'skills'"):
        build_effective(ws, "personal")


def test_scalar_list_key_in_base_layer_raises(ws):
    # even when no base layer defines the key as a list first
    (ws / "configs" / "common.yaml").write_text("skills: alpha\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"'skills' must be a list"):
        build_effective(ws, None)


def test_nested_list_union_still_applies():
    base = {"secrets": {"optional": ["A"]}}
    over = {"secrets": {"optional": ["A", "B"]}}
    assert merge(base, over) == {"secrets": {"optional": ["A", "B"]}}