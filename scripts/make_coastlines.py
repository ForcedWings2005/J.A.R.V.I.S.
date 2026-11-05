"""Makes static/data/coastlines.json, the coastlines the Weather globe draws.

Source: Natural Earth 1:110m coastlines, v4.1.0, public domain
(https://www.naturalearthdata.com). The file used, downloaded 2026-11-05 with the owner's
permission:
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/693f11422f4e08d2da4566b854dda53eb7c39fb3/geojson/ne_110m_coastline.geojson
139,907 bytes, SHA-256 851f581ff5ffb844deed8ae1a9ce22e3c4bb3d74fa342cadb5d8e39b41ae7c3c.

Usage, from the project folder (the download is read as data, never run):
    python -I scripts/make_coastlines.py path/to/ne_110m_coastline.geojson

Only the standard library. Coordinates are rounded to 1 decimal place (about 11 km, finer
than a pixel on the globe), which keeps the file small.
Spec: docs/specs/2026-11-05-weather-space.md ("Files").
"""
import json
import math
import sys
from pathlib import Path

SOURCE = "Natural Earth 1:110m coastlines, v4.1.0, public domain"
OUT = Path(__file__).resolve().parent.parent / "static" / "data" / "coastlines.json"


def _point(p):
    """A [lon, lat] pair of finite numbers in range, rounded, or None."""
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        return None
    lon, lat = p[0], p[1]
    for v in (lon, lat):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return [round(lon, 1), round(lat, 1)]


def _line(coords) -> list:
    """Clean points, without the same point twice in a row."""
    out = []
    for p in coords if isinstance(coords, list) else []:
        q = _point(p)
        if q is not None and (not out or out[-1] != q):
            out.append(q)
    return out


def convert(geojson: dict) -> dict:
    """Every LineString and MultiLineString as lists of [lon, lat]; anything else is skipped."""
    lines = []
    for feature in geojson.get("features", []) if isinstance(geojson, dict) else []:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            continue
        kind, coords = geometry.get("type"), geometry.get("coordinates")
        parts = [coords] if kind == "LineString" else coords if kind == "MultiLineString" else []
        for part in parts if isinstance(parts, list) else []:
            line = _line(part)
            if len(line) >= 2:
                lines.append(line)
    return {"source": SOURCE, "lines": lines}


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        sys.exit("usage: python -I scripts/make_coastlines.py path/to/ne_110m_coastline.geojson")
    data = convert(json.loads(Path(argv[1]).read_text()))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    points = sum(len(line) for line in data["lines"])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(data['lines'])} lines, {points} points)")


if __name__ == "__main__":
    main(sys.argv)
