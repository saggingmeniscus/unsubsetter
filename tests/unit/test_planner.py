from pathlib import Path

from unsubsetter.planner import Replace, Skip, Plan


def test_replace_action_has_required_fields():
    r = Replace(record=None, source_path=Path("/x.ttf"), ttc_face=None)
    assert r.source_path == Path("/x.ttf")
    assert r.ttc_face is None


def test_skip_action_has_reason():
    s = Skip(record=None, reason="not subsetted")
    assert s.reason == "not subsetted"


def test_plan_render_lists_actions():
    plan = Plan(actions=[
        Skip(record=_fake_record("Foo", subset_prefix=None), reason="not subsetted"),
    ])
    text = plan.render()
    assert "Foo" in text
    assert "not subsetted" in text


def _fake_record(ps_name: str, subset_prefix: str | None):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type0", descendant_subtype="CIDFontType2",
        encoding="Identity-H", has_font_file=True, font_file_kind="FontFile2",
        used_cids=frozenset(),
    )


from unsubsetter.planner import build_plan
from unsubsetter.font_index import FontIndex, FontIndexEntry


def _idx_with(ps_name: str, path: str = "/disk/x.ttf", ttc_face=None) -> FontIndex:
    e = FontIndexEntry(
        path=Path(path), ttc_face=ttc_face,
        ps_name=ps_name, full_name=ps_name, family=ps_name, subfamily="",
    )
    return FontIndex({_norm(ps_name): e})


def _norm(s):
    from unsubsetter.font_index import normalize_name
    return normalize_name(s)


def test_build_plan_replaces_resolvable_cid_truetype():
    rec = _fake_record("Preciosa", subset_prefix="ABCDEF")
    idx = _idx_with("Preciosa")
    plan = build_plan([rec], idx)
    assert len(plan.replaces()) == 1
    assert plan.replaces()[0].source_path == Path("/disk/x.ttf")


def test_build_plan_skips_non_subset_font():
    rec = _fake_record("Preciosa", subset_prefix=None)
    plan = build_plan([rec], _idx_with("Preciosa"))
    assert plan.skips()[0].reason == "not subsetted"


def test_build_plan_skips_cff_font():
    rec = _fake_record_cff("BradleyInitials", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("BradleyInitials"))
    assert "CFF" in plan.skips()[0].reason


def test_build_plan_skips_type1_font():
    rec = _fake_record_type1("CMSY7", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("CMSY7"))
    assert "Type1" in plan.skips()[0].reason or "Type 1" in plan.skips()[0].reason


def test_build_plan_skips_unresolvable_font():
    rec = _fake_record("MysteryFont", subset_prefix="ABCDEF")
    plan = build_plan([rec], FontIndex({}))
    assert "not found" in plan.skips()[0].reason.lower()


def test_build_plan_respects_only_filter():
    rec_a = _fake_record("FontA", subset_prefix="ABCDEF")
    rec_b = _fake_record("FontB", subset_prefix="ABCDEF")
    idx = FontIndex({_norm("FontA"): _entry("FontA"), _norm("FontB"): _entry("FontB")})
    plan = build_plan([rec_a, rec_b], idx, only={"FontA"})
    names = [a.record.ps_name for a in plan.replaces()]
    assert names == ["FontA"]
    assert any(a.reason == "not selected by --only" for a in plan.skips())


def test_build_plan_respects_exclude_filter():
    rec = _fake_record("FontA", subset_prefix="ABCDEF")
    plan = build_plan([rec], _idx_with("FontA"), exclude={"FontA"})
    assert plan.skips()[0].reason == "excluded by --exclude"


def _entry(name):
    return FontIndexEntry(path=Path("/x"), ttc_face=None,
                          ps_name=name, full_name=name, family=name, subfamily="")


def _fake_record_cff(ps_name, subset_prefix):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type0", descendant_subtype="CIDFontType0",
        encoding="Identity-H", has_font_file=True, font_file_kind="FontFile3",
        used_cids=frozenset(),
    )


def _fake_record_type1(ps_name, subset_prefix):
    from unsubsetter.inspector import FontRecord
    return FontRecord(
        font_obj=None, base_font=ps_name, subset_prefix=subset_prefix,
        ps_name=ps_name, subtype="Type1", descendant_subtype=None,
        encoding="Builtin", has_font_file=True, font_file_kind="FontFile",
        used_cids=frozenset(),
    )
