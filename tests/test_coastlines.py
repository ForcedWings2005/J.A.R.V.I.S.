"""The globe's coastlines: the script that makes them, and the file it made
(docs/specs/2026-11-05-weather-space.md, "Files")."""
import importlib.util
import json

import config

_spec = importlib.util.spec_from_file_location(
    "make_coastlines", config.ROOT / "scripts" / "make_coastlines.py")
make_coastlines = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_coastlines)

COASTLINES = config.STATIC_DIR / "data" / "coastlines.json"


def test_lines_are_rounded_and_cleaned():
    geo = {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "LineString",
                      "coordinates": [[1.04, 2.06], [1.01, 2.09], [3.5, 4.5]]}},
        {"geometry": {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[5, 5]]]}},
        {"geometry": {"type": "Point", "coordinates": [9, 9]}},
        {"geometry": {"type": "LineString",
                      "coordinates": [[1, "x"], [200, 0], [2, 2], [3, 3]]}},
        {"geometry": None},
        "not a feature",
    ]}
    out = make_coastlines.convert(geo)
    assert out["lines"] == [[[1.0, 2.1], [3.5, 4.5]], [[0, 0], [1, 1]], [[2, 2], [3, 3]]]
    assert "public domain" in out["source"]


def test_the_committed_file_is_small_and_sane():
    size = COASTLINES.stat().st_size
    data = json.loads(COASTLINES.read_text())
    assert 10_000 < size < 100_000
    assert len(data["lines"]) > 50
    for line in data["lines"]:
        assert len(line) >= 2
        assert all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in line)
