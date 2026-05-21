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
