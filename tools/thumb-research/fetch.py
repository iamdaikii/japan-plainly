#!/usr/bin/env python3
"""One-off research: collect thumbnails of well-performing English videos that
explain Japanese culture, and build contact sheets. No API key.
Usage: python3 fetch.py <out_dir>"""
import io, json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw, ImageFont

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
           "Cookie": "CONSENT=YES+1; SOCS=CAI"}
QUERIES = {
    "culture": ["why do japanese people", "japanese culture explained", "why japan is so clean",
                "why are japanese trains so quiet", "why japan doesn't tip", "japan etiquette rules explained",
                "things not to do in japan", "why japanese say sumimasen", "japan explained",
                "why japan does that", "why is japan like this"],
    "animation": ["japan explained animation", "japanese culture animated explainer", "why japan animated",
                  "stick figure explains japan", "history of japan animated", "countries explained animation stick figure",
                  "culture explained stick figure animation", "stick figure explainer"],
    "whyjapan": ["Why Japan channel sumimasen thank you not just sorry", "\"Why Japan\" why japanese people"],
}
MIN_VIEWS = {"culture": 300000, "animation": 200000, "whyjapan": 0}

def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                b = r.read()
                return b if binary else b.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 * (i + 1))
    raise err

def views(t):
    if not t: return 0
    m = re.search(r"([\d,.]+)\s*([KMB]?)", t)
    if not m: return 0
    try: return int(float(m.group(1).replace(",", "")) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])
    except ValueError: return 0

def secs(t):
    s = 0
    for x in (t or "0").split(":"):
        if x.isdigit(): s = s * 60 + int(x)
    return s

def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)

def search(q, group):
    html = get("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    out = []
    if not m: return out
    for d in walk(json.loads(m.group(1))):
        vr = d.get("videoRenderer")
        if not (vr and vr.get("videoId")): continue
        av = ""
        try: av = vr["channelThumbnailSupportedRenderers"]["channelThumbnailWithLinkRenderer"]["thumbnail"]["thumbnails"][0]["url"]
        except Exception: pass
        out.append({"id": vr["videoId"], "group": group, "query": q,
            "title": "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", [])),
            "channel": "".join(r.get("text", "") for r in vr.get("ownerText", {}).get("runs", [])),
            "views": views(vr.get("viewCountText", {}).get("simpleText")),
            "len": secs(vr.get("lengthText", {}).get("simpleText")),
            "age": vr.get("publishedTimeText", {}).get("simpleText", ""), "avatar": av})
    return out

def font(sz, bold=False):
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")
    return ImageFont.truetype(p, sz) if os.path.exists(p) else ImageFont.load_default()

def img(url):
    try: return Image.open(io.BytesIO(get(url, True))).convert("RGB")
    except Exception: return None

def asc(s, n): return s[:n].encode("ascii", "replace").decode()

def sheet(items, path, cols=4):
    W, H, PAD, CAP = 320, 180, 12, 62
    rows = max(1, (len(items) + cols - 1) // cols)
    im = Image.new("RGB", (cols * (W + PAD) + PAD, rows * (H + CAP + PAD) + PAD), "white")
    dr = ImageDraw.Draw(im)
    for i, it in enumerate(items):
        x = PAD + (i % cols) * (W + PAD); y = PAD + (i // cols) * (H + CAP + PAD)
        t = img("https://i.ytimg.com/vi/%s/mqdefault.jpg" % it["id"])
        if t: im.paste(t.resize((W, H)), (x, y))
        dr.text((x, y + H + 3), "%d. %s views | %s" % (i + 1, "{:,}".format(it["views"]), it["age"]), fill="black", font=font(13, True))
        dr.text((x, y + H + 21), asc(it["channel"], 40), fill="#444", font=font(12))
        dr.text((x, y + H + 38), asc(it["title"], 48), fill="#444", font=font(12))
    im.save(path, quality=88)

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    allv = {}
    for g, qs in QUERIES.items():
        for q in qs:
            try: res = search(q, g)
            except Exception as e:  # noqa: BLE001
                print("fail", q, e); continue
            print(q, len(res))
            for v in res:
                allv.setdefault(v["id"], v)
            time.sleep(1.5)
    picked = {}
    for g in QUERIES:
        vs = [v for v in allv.values() if v["group"] == g and v["views"] >= MIN_VIEWS[g] and v["len"] >= 120]
        if g == "culture": vs = [v for v in vs if re.search(r"japan|tokyo", v["title"], re.I)]
        if g == "whyjapan": vs = [v for v in vs if v["channel"].strip().lower() == "why japan"]
        vs.sort(key=lambda v: -v["views"])
        seen, keep = {}, []
        for v in vs:
            if g != "whyjapan" and seen.get(v["channel"], 0) >= 2: continue
            seen[v["channel"]] = seen.get(v["channel"], 0) + 1; keep.append(v)
        picked[g] = keep[:24]
        sheet(picked[g], os.path.join(out, "sheet-%s.jpg" % g))
    ch = {}
    for g in picked:
        for v in picked[g]:
            if v["avatar"] and v["channel"] not in ch: ch[v["channel"]] = v["avatar"]
    names = list(ch)[:40]
    S = 120; cols = 8; rows = max(1, (len(names) + cols - 1) // cols)
    im = Image.new("RGB", (cols * (S + 16) + 16, rows * (S + 40) + 16), "white"); dr = ImageDraw.Draw(im)
    for i, n in enumerate(names):
        x = 16 + (i % cols) * (S + 16); y = 16 + (i // cols) * (S + 40)
        u = re.sub(r"=s\d+", "=s176", ch[n]); u = ("https:" + u) if u.startswith("//") else u
        a = img(u)
        if a:
            a = a.resize((S, S)); im.paste(a, (x, y))
            sm = a.resize((40, 40)); im.paste(Image.new("RGB", (44, 44), "white"), (x + S - 44, y + S - 44)); im.paste(sm, (x + S - 42, y + S - 42))
        dr.text((x, y + S + 4), asc(n, 18), fill="black", font=font(11))
    im.save(os.path.join(out, "sheet-avatars.jpg"), quality=88)
    for g in picked:
        for v in picked[g]: v.pop("avatar", None)
    json.dump(picked, open(os.path.join(out, "list.json"), "w"), ensure_ascii=False, indent=1)

main()
