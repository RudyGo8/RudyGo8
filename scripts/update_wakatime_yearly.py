import json
import math
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # py<3.9 fallback


ROOT = Path(__file__).resolve().parents[1]
STATS_DIR = ROOT / "stats"
JSON_FILE = STATS_DIR / "yearly.json"
SVG_FILE = STATS_DIR / "yearly.svg"

API_KEY = os.environ["WAKATIME_API_KEY"]
TZ_NAME = os.getenv("WAKATIME_TZ", "Asia/Shanghai")
BACKFILL_DAYS = int(os.getenv("WAKATIME_BACKFILL_DAYS", "7"))
TOP_N = int(os.getenv("WAKATIME_TOP_N", "12"))

tz = ZoneInfo(TZ_NAME)


def fetch_summary_for_day(day_str: str) -> dict:
    params = {
        "start": day_str,
        "end": day_str,
        "timezone": TZ_NAME,
        "api_key": API_KEY,
    }
    url = "https://api.wakatime.com/api/v1/users/current/summaries?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data.get("data", [])
    if not items:
        return {
            "date": day_str,
            "total_seconds": 0.0,
            "languages": {},
            "editors": {},
        }

    day = items[0]
    languages = {
        x["name"]: float(x.get("total_seconds", 0))
        for x in day.get("languages", [])
        if x.get("name")
    }
    editors = {
        x["name"]: float(x.get("total_seconds", 0))
        for x in day.get("editors", [])
        if x.get("name")
    }
    total_seconds = float(day.get("grand_total", {}).get("total_seconds", 0))

    print(f"[DEBUG] {day_str} total_seconds={total_seconds}")

    return {
        "date": day_str,
        "total_seconds": total_seconds,
        "languages": languages,
        "editors": editors,
    }


def load_store() -> dict:
    if JSON_FILE.exists():
        return json.loads(JSON_FILE.read_text(encoding="utf-8"))
    return {"days": {}, "updated_at": None}


def save_store(store: dict) -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def build_year_language_stats(store: dict, year: int, top_n: int = 10) -> dict:
    languages = defaultdict(float)
    total_seconds = 0.0

    for day_str, day in store.get("days", {}).items():
        if not str(day_str).startswith(str(year)):
            continue

        day_total = float(day.get("total_seconds", 0))
        total_seconds += day_total

        for name, sec in day.get("languages", {}).items():
            sec = float(sec)
            if sec > 0:
                languages[name] += sec

    items = sorted(languages.items(), key=lambda x: x[1], reverse=True)

    top_items = items[:top_n]
    other_sum = sum(sec for _, sec in items[top_n:])
    if other_sum > 0:
        top_items.append(("Other", other_sum))

    return {
        "year": year,
        "total_seconds": total_seconds,
        "languages": top_items,
    }
    

def fmt_percent(part: float, total: float) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part / total * 100:.2f}%"


def fmt_hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h"


def polar_to_cartesian(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg - 90)
    return cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)


def describe_arc(cx: float, cy: float, r: float, start_angle: float, end_angle: float) -> str:
    start_x, start_y = polar_to_cartesian(cx, cy, r, end_angle)
    end_x, end_y = polar_to_cartesian(cx, cy, r, start_angle)
    large_arc_flag = 1 if (end_angle - start_angle) > 180 else 0
    return (
        f"M {start_x:.2f} {start_y:.2f} "
        f"A {r} {r} 0 {large_arc_flag} 0 {end_x:.2f} {end_y:.2f}"
    )


def generate_donut_svg(stats: dict) -> str:
    width = 980
    height = 540
    bg = "#0d1117"
    border = "#30363d"
    title_color = "#58a6ff"
    text_color = "#c9d1d9"
    sub_text = "#8b949e"
    track_color = "#161b22"

    cx = 690
    cy = 270
    radius = 130
    stroke_width = 64

    colors = [
        "#316dca", "#00c853", "#1e88e5", "#455a64", "#c51162",
        "#c0b050", "#d84315", "#3949ab", "#fb8c00", "#8e24aa",
        "#00897b", "#6d4c41", "#ff7043"
    ]

    total = float(stats["total_seconds"])
    items = stats["languages"]

    arcs = []
    legends = []

    if total > 0 and items:
        current_angle = 0.0
        for i, (name, sec) in enumerate(items):
            angle = (sec / total) * 360.0
            start_angle = current_angle
            end_angle = current_angle + angle
            color = colors[i % len(colors)]

            path_d = describe_arc(cx, cy, radius, start_angle, end_angle)
            arcs.append(
                f'<path d="{path_d}" stroke="{color}" stroke-width="{stroke_width}" fill="none" stroke-linecap="butt" />'
            )

            legend_y = 92 + i * 28
            legends.append(
                f'<rect x="36" y="{legend_y - 11}" width="12" height="12" rx="2" fill="{color}" />'
                f'<text x="56" y="{legend_y}" font-size="16" fill="{text_color}" '
                f'font-family="Arial, Helvetica, sans-serif">'
                f'{name} ({fmt_percent(sec, total)})</text>'
            )
            current_angle = end_angle

    total_hours = total / 3600.0

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="WakaTime yearly language stats">
  <rect width="100%" height="100%" fill="{bg}"/>
  <rect x="10" y="10" width="{width-20}" height="{height-20}" fill="none" stroke="{border}"/>

  <text x="{width/2}" y="42" text-anchor="middle" font-size="24" fill="{title_color}" font-family="Arial, Helvetica, sans-serif">
    Languages in {stats["year"]} (Powered by wakatime.com)
  </text>

  {''.join(legends)}

  <circle cx="{cx}" cy="{cy}" r="{radius}" stroke="{track_color}" stroke-width="{stroke_width}" fill="none"/>
  {''.join(arcs)}
  <circle cx="{cx}" cy="{cy}" r="88" fill="{bg}"/>

  <text x="{cx}" y="{cy - 6}" text-anchor="middle" font-size="28" fill="{text_color}" font-family="Arial, Helvetica, sans-serif">
    {total_hours:.1f}h
  </text>
  <text x="{cx}" y="{cy + 24}" text-anchor="middle" font-size="14" fill="{sub_text}" font-family="Arial, Helvetica, sans-serif">
    This Year
  </text>
</svg>"""


def refresh_recent_days(store: dict, today) -> dict:
    # 每次回填最近 N 天，避免日切和汇总延迟
    start_day = today - timedelta(days=max(BACKFILL_DAYS - 1, 0))
    end_day = today

    current = start_day
    while current <= end_day:
        day_str = current.isoformat()
        store["days"][day_str] = fetch_summary_for_day(day_str)
        current += timedelta(days=1)

    return store


def prune_future_days(store: dict, today) -> dict:
    valid_days = {}
    for day_str, value in store.get("days", {}).items():
        try:
            day_obj = datetime.fromisoformat(day_str).date()
        except ValueError:
            continue
        if day_obj <= today:
            valid_days[day_str] = value
    store["days"] = valid_days
    return store


def main():
    now = datetime.now(tz)
    today = now.date()

    store = load_store()
    store = prune_future_days(store, today)
    store = refresh_recent_days(store, today)

    store["updated_at"] = now.isoformat()
    save_store(store)

    year_stats = build_year_language_stats(store, now.year, TOP_N)
    svg = generate_donut_svg(year_stats)
    SVG_FILE.write_text(svg, encoding="utf-8")

    print(f"[INFO] updated {SVG_FILE}")
    print(f"[INFO] total_seconds={year_stats['total_seconds']}")
    print(f"[INFO] languages={len(year_stats['languages'])}")


if __name__ == "__main__":
    main()
