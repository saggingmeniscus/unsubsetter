from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont

from unsubsetter.applier import load_full_font_bytes


def test_load_full_font_bytes_from_ttf(make_ttf):
    path = make_ttf("a.ttf", ps_name="A")
    data = load_full_font_bytes(path, ttc_face=None)
    # Should be a parseable standalone TTF.
    tt = TTFont(BytesIO(data))
    assert tt["name"].getDebugName(6) == "A"


def test_load_full_font_bytes_from_ttc_face(make_ttc):
    path = make_ttc("bundle.ttc", faces=[
        {"ps_name": "FaceA"},
        {"ps_name": "FaceB"},
    ])
    data_b = load_full_font_bytes(path, ttc_face=1)
    tt = TTFont(BytesIO(data_b))
    assert tt["name"].getDebugName(6) == "FaceB"
