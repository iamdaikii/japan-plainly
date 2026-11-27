#!/usr/bin/env python3
"""Find street-interview videos that are doing unusually well this week.

No API key needed: uses each channel's public RSS feed (latest 15 videos with
view counts) plus YouTube's public search page filtered to "this week".

Usage: python3 fetch.py <channels.json> <out_dir>
Writes out_dir/latest.json, out_dir/latest.md, out_dir/history/<date>.json
"""
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
           "Cookie": "CONSENT=YES+1; SOCS=CAI"}
NS = {"a": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}
NOW = datetime.now(timezone.utc)
WINDOW = timedelta(days=7)
MIN_RATIO = 1.5


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 * (i + 1))
    raise err


def resolve_handle(handle, cache):
    if handle in cache:
        return cache[handle]
    html = get("https://www.youtube.com/" + urllib.parse.quote(handle))
    for pat in (r'"externalId":"(UC[\w-]{22})"',
                r'<meta itemprop="identifier" content="(UC[\w-]{22})"',
                r'"channelId":"(UC[\w-]{22})"'):
        m = re.search(pat, html)
        if m:
            cache[handle] = m.group(1)
            return m.group(1)
    return None


def channel_videos(cid):
    xml = get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        stats = e.find("media:group/media:community/media:statistics", NS)
        thumb = e.find("media:group/media:thumbnail", NS)
        out.append({
            "id": vid,
            "title": e.findtext("a:title", namespaces=NS),
            "channel": e.findtext("a:author/a:name", namespaces=NS),
            "published": e.findtext("a:published", namespaces=NS),
            "views": int(stats.get("views", 0)) if stats is not None else 0,
            "thumbnail": thumb.get("url") if thumb is not None else None,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


def parse_views(text):
    if not text:
        return 0
    t = text.replace(",", "").lower()
    m = re.search(r"([\d.]+)\s*([km]?)", t)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2), 1))


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def search_week(query):
    url = ("https://www.youtube.com/results?search_query="
           + urllib.parse.quote_plus(query) + "&sp=EgIIAw%253D%253D")
    html = get(url)
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    out = []
    for d in walk(data):
        vr = d.get("videoRenderer")
        if vr and vr.get("videoId"):
            out.append({
                "id": vr["videoId"],
                "title": "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", [])),
                "channel": "".join(r.get("text", "") for r in vr.get("ownerText", {}).get("runs", [])),
                "views": parse_views(vr.get("viewCountText", {}).get("simpleText")),
                "age": vr.get("publishedTimeText", {}).get("simpleText"),
                "url": f"https://www.youtube.com/watch?v={vr['videoId']}",
                "query": query,
            })
        sl = d.get("shortsLockupViewModel")
        if sl:
            vid = (sl.get("onTap", {}).get("innertubeCommand", {})
                   .get("reelWatchEndpoint", {}).get("videoId"))
            meta = sl.get("overlayMetadata", {})
            if vid:
                out.append({
                    "id": vid,
                    "title": meta.get("primaryText", {}).get("content", ""),
                    "channel": "",
                    "views": parse_views(meta.get("secondaryText", {}).get("content")),
                    "age": "this week",
                    "url": f"https://www.youtube.com/shorts/{vid}",
                    "query": query,
                })
    return out


def main():
    cfg_path, out_dir = sys.argv[1], sys.argv[2]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    os.makedirs(os.path.join(out_dir, "history"), exist_ok=True)
    cache_path = os.path.join(out_dir, "handle-cache.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

    outliers, errors, checked = [], [], 0
    for ch in cfg["channels"]:
        try:
            cid = ch.get("id") or resolve_handle(ch["handle"], cache)
            if not cid:
                errors.append(f"{ch['name']}: channel not found ({ch.get('handle')})")
                continue
            vids = channel_videos(cid)
            checked += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{ch['name']}: {type(e).__name__}: {e}")
            continue
        views = [v["views"] for v in vids if v["views"]]
        if len(views) < 4:
            continue
        med = statistics.median(views)
        for v in vids:
            pub = datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
            if NOW - pub > WINDOW or not med:
                continue
            ratio = v["views"] / med
            if ratio >= MIN_RATIO:
                v.update(ratio=round(ratio, 1), median=int(med), group=ch["group"],
                         days_old=(NOW - pub).days)
                outliers.append(v)
        time.sleep(1)
    outliers.sort(key=lambda v: v["ratio"], reverse=True)

    found, seen = [], set()
    for q in cfg.get("search_queries", []):
        try:
            for v in search_week(q):
                if v["id"] not in seen:
                    seen.add(v["id"])
                    found.append(v)
        except Exception as e:  # noqa: BLE001
            errors.append(f"search '{q}': {type(e).__name__}: {e}")
        time.sleep(2)
    found.sort(key=lambda v: v["views"], reverse=True)

    result = {"generated_at": NOW.isoformat(), "channels_checked": checked,
              "channel_outliers": outliers[:20], "search_top_week": found[:20],
              "errors": errors}
    day = NOW.strftime("%Y-%m-%d")
    for p in ("latest.json", f"history/{day}.json"):
        with open(os.path.join(out_dir, p), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=1)

    jst = (NOW + timedelta(hours=9)).strftime("%m/%d %H:%M")
    lines = [f"# 伸びている街頭インタビュー（直近7日・{jst} JST）", ""]
    lines.append("## いつもより伸びた動画（チャンネルの普段の再生数の何倍か）")
    if outliers:
        for v in outliers[:5]:
            lines.append(f"- {v['ratio']}倍｜{v['channel']}｜{v['title']}｜"
                         f"{v['views']:,}回（普段{v['median']:,}回）｜{v['url']}")
    else:
        lines.append("- 今週は目立って伸びた動画なし")
    lines += ["", "## 今週の検索上位（再生数順）"]
    for v in found[:5]:
        ch = f"{v['channel']}｜" if v["channel"] else ""
        lines.append(f"- {v['views']:,}回｜{ch}{v['title']}｜{v['url']}")
    if not found:
        lines.append("- 取得できず")
    if errors:
        lines += ["", "## 取得エラー（統括が直す用）"] + [f"- {e}" for e in errors]
    with open(os.path.join(out_dir, "latest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
