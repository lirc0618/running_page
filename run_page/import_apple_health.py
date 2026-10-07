"""Build the static running page from an Apple Health GPX route export.

Usage: python run_page/import_apple_health.py
The source GPX files stay local; only the compact page data and SVGs are written.
"""

import argparse
import calendar
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
LOCAL_TIMEZONE = timezone.utc
try:
    from zoneinfo import ZoneInfo

    LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
except Exception:
    pass


def distance_m(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    h = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def encode_polyline(points):
    out = []
    previous = [0, 0]
    for lat, lon in points:
        for axis, value in enumerate((lat, lon)):
            current = round(value * 100000)
            delta = current - previous[axis]
            previous[axis] = current
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
    return "".join(out)


def read_route(path):
    first = last = None
    previous_point = None
    kept = []
    distance = 0.0
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag.rsplit("}", 1)[-1] != "trkpt":
            continue
        try:
            point = (float(element.attrib["lat"]), float(element.attrib["lon"]))
            time_text = next(
                (
                    child.text
                    for child in element
                    if child.tag.rsplit("}", 1)[-1] == "time"
                ),
                None,
            )
            when = (
                datetime.fromisoformat(time_text.replace("Z", "+00:00"))
                if time_text
                else None
            )
        except (KeyError, TypeError, ValueError):
            element.clear()
            continue
        if when is None:
            element.clear()
            continue
        if first is None:
            first = when
            kept.append(point)
        if previous_point is not None:
            step = distance_m(previous_point, point)
            if step <= 250:
                distance += step
        if distance_m(kept[-1], point) >= 25:
            kept.append(point)
        last, previous_point = when, point
        element.clear()
    if first is None or last is None or last <= first or distance < 100:
        return None
    if kept[-1] != previous_point:
        kept.append(previous_point)
    elapsed = int((last - first).total_seconds())
    if elapsed <= 0:
        return None
    local = first.astimezone(LOCAL_TIMEZONE)
    return {
        "run_id": int(first.timestamp() * 1000),
        "name": "Apple Health Run",
        "distance": round(distance, 2),
        "moving_time": str(timedelta(seconds=elapsed)),
        "type": "Run",
        "start_date": first.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date_local": local.strftime("%Y-%m-%d %H:%M:%S"),
        "location_country": "",
        "summary_polyline": "",
        "average_heartrate": None,
        "average_speed": round(distance / elapsed, 3),
        "_end": last,
        "_seconds": elapsed,
        "_points": kept,
    }


def heatmap_svg(activities, title, year=None, min_run_km=0):
    daily = defaultdict(float)
    for activity in activities:
        date = activity["start_date_local"][:10]
        if activity["distance"] >= min_run_km * 1000 and (
            year is None or date.startswith(str(year))
        ):
            daily[date] += activity["distance"] / 1000
    years = [year] if year else sorted({int(date[:4]) for date in daily})
    cell, gap, row_height = 10, 3, 120
    width, height = 760, 55 + row_height * len(years)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        '<rect width="100%" height="100%" fill="#222222"/>',
        f'<text x="20" y="30" fill="#ffffff" font-family="Arial,sans-serif" font-size="20">{escape(title)}</text>',
    ]
    colors = ("#343a40", "#27546a", "#2380a0", "#4dd2ff", "#ffff00")
    for row, current_year in enumerate(years):
        y0 = 63 + row * row_height
        parts.append(
            f'<text x="20" y="{y0 + 9}" fill="#ffffff" font-family="Arial,sans-serif" font-size="13">{current_year}</text>'
        )
        first_day = datetime(current_year, 1, 1).date()
        days = 366 if calendar.isleap(current_year) else 365
        for offset in range(days):
            date = first_day.fromordinal(first_day.toordinal() + offset)
            week = (offset + first_day.weekday()) // 7
            km = daily.get(date.isoformat(), 0)
            level = (
                0 if km == 0 else 1 if km < 3 else 2 if km < 7 else 3 if km < 15 else 4
            )
            x = 60 + week * (cell + gap)
            y = y0 + date.weekday() * (cell + gap)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{colors[level]}"><title>{date}: {km:.1f} km</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "Workouts")
    parser.add_argument("--athlete", default="lircOS")
    args = parser.parse_args()
    files = sorted(args.source.glob("*.gpx"))
    if not files:
        parser.error(f"No GPX files found in {args.source}")
    activities = []
    skipped = []
    seen = set()
    for index, path in enumerate(files, 1):
        try:
            activity = read_route(path)
        except ET.ParseError:
            activity = None
        if activity and activity["run_id"] not in seen:
            seen.add(activity["run_id"])
            activities.append(activity)
        else:
            skipped.append(path.name)
        if index % 500 == 0:
            print(f"Read {index}/{len(files)} routes", flush=True)
    if not activities:
        parser.error("No usable routes were found; existing page data was left intact")
    activities.sort(key=lambda item: item["start_date_local"])
    merged = []
    for activity in activities:
        if merged:
            previous = merged[-1]
            gap = (
                activity["_end"].astimezone(LOCAL_TIMEZONE)
                - previous["_end"].astimezone(LOCAL_TIMEZONE)
            ).total_seconds()
            start_gap = (
                datetime.fromisoformat(activity["start_date_local"]).replace(
                    tzinfo=LOCAL_TIMEZONE
                )
                - previous["_end"].astimezone(LOCAL_TIMEZONE)
            ).total_seconds()
            if 0 < start_gap < 3600 and gap > 0:
                previous["distance"] += activity["distance"]
                previous["_seconds"] += activity["_seconds"]
                previous["_end"] = activity["_end"]
                previous["_points"].extend(activity["_points"])
                continue
        merged.append(activity)
    activities = merged
    streak, prior_date = 0, None
    for activity in activities:
        activity["distance"] = round(activity["distance"], 2)
        activity["moving_time"] = str(timedelta(seconds=activity["_seconds"]))
        activity["average_speed"] = round(
            activity["distance"] / activity["_seconds"], 3
        )
        activity["summary_polyline"] = encode_polyline(activity.pop("_points"))
        del activity["_seconds"], activity["_end"]
        date = datetime.strptime(activity["start_date_local"][:10], "%Y-%m-%d").date()
        if date != prior_date:
            streak = streak + 1 if prior_date and (date - prior_date).days == 1 else 1
        activity["streak"] = streak
        prior_date = date
    data_path = ROOT / "src" / "static" / "activities.json"
    data_path.write_text(
        json.dumps(activities, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    assets = ROOT / "assets"
    (assets / "github.svg").write_text(
        heatmap_svg(activities, f"{args.athlete} Running"), encoding="utf-8"
    )
    (assets / "grid.svg").write_text(
        heatmap_svg(activities, f"{args.athlete} Runs Over 10 km", min_run_km=10),
        encoding="utf-8",
    )
    years = {int(item["start_date_local"][:4]) for item in activities}
    for year in years:
        year_svg = heatmap_svg(activities, f"{year} Running", year)
        (assets / f"year_{year}.svg").write_text(year_svg, encoding="utf-8")
        (assets / f"github_{year}.svg").write_text(year_svg, encoding="utf-8")
    for path in assets.glob("year_*.svg"):
        if int(path.stem.split("_")[1]) not in years:
            path.unlink()
    for path in assets.glob("github_*.svg"):
        if int(path.stem.split("_")[1]) not in years:
            path.unlink()
    print(
        f"Imported {len(activities)} runs from {len(files)} files; skipped {len(skipped)} routes"
    )
    print(
        f"Date range: {activities[0]['start_date_local']} to {activities[-1]['start_date_local']}"
    )
    if skipped:
        print("Skipped examples:", ", ".join(skipped[:10]))


if __name__ == "__main__":
    main()
