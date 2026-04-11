import json
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
            "total_seconds": 0,
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


def build_year_stats(store: dict, year: int) -> dict:
    monthly = defaultdict(float)
    languages = defaultdict(float)
    editors = defaultdict(float)
    total_seconds = 0.0

    for day_str, day in store.get("days", {}).items():
        if not day_str.startswith(str(year)):
            continue
        total_seconds += float(day.get("total_seconds", 0))
        month = int(day_str[5:7])
        monthly[month] += float(day.get("total_seconds", 0))

        for name, sec in day.get("languages", {}).items():
            languages[name] += float(sec)
        for name, sec in day.get("editors", {}).items():
            editors[name] += float(sec)

    return {
        "year": year,
        "total_seconds": total_seconds,
        "monthly": {m: monthly.get(m, 0.0) for m in range(1, 13)},
        "top_languages": sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_editors": sorted(editors.items(), key=lambda x: x[1], reverse=True)[:5],
    }


def fmt_hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h"


def generate_svg(stats: dict) -> str:
    width = 900
    height = 420
    left = 70
    bottom = 330
    chart_w = 760
    chart_h = 180
    bar_w = 42
    gap = 20

    monthly_values = [stats["monthly"][m] / 3600 for m in range(1, 13)]
    max_val = max(monthly_values) if max(monthly_values) > 0 else 1

    bars = []
    labels = []
    for i, val in enumerate(monthly_values):
        x = left + i * (bar_w + gap)
        h = (val / max_val) * chart_h
        y = bottom - h
        bars.append(
            f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="6" fill="#58a6ff" />'
        )
        labels.append(
            f'<text x="{x + bar_w / 2}" y="{bottom + 22}" text-anchor="middle" '
            f'font-size="12" fill="#8b949e">{i+1}月</text>'
        )

    top_lang = " / ".join(
        f"{name} {fmt_hours(sec)}" for name, sec in stats["top_languages"]
    ) or "暂无数据"
    top_editor = " / ".join(
        f"{name} {fmt_hours(sec)}" for name, sec in stats["top_editors"]
    ) or "暂无数据"

    total_hours = stats["total_seconds"] / 3600

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="WakaTime yearly stats">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="40" y="50" font-size="28" fill="#c9d1d9" font-family="Arial, Helvetica, sans-serif">WakaTime {stats["year"]} 年度统计</text>
  <text x="40" y="85" font-size="18" fill="#58a6ff" font-family="Arial, Helvetica, sans-serif">总计：{total_hours:.1f} 小时</text>

  <line x1="{left}" y1="{bottom}" x2="{left + chart_w}" y2="{bottom}" stroke="#30363d" />
  <line x1="{left}" y1="{bottom - chart_h}" x2="{left}" y2="{bottom}" stroke="#30363d" />

  {''.join(bars)}
  {''.join(labels)}

  <text x="40" y="380" font-size="14" fill="#8b949e" font-family="Arial, Helvetica, sans-serif">Top Languages: {top_lang}</text>
  <text x="40" y="405" font-size="14" fill="#8b949e" font-family="Arial, Helvetica, sans-serif">Top Editors: {top_editor}</text>
</svg>'''


def main():
    now = datetime.now(tz)
    yesterday = (now - timedelta(days=1)).date().isoformat()

    store = load_store()
    store["days"][yesterday] = fetch_summary_for_day(yesterday)
    store["updated_at"] = now.isoformat()
    save_store(store)

    year_stats = build_year_stats(store, now.year)
    svg = generate_svg(year_stats)
    SVG_FILE.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
