#!/usr/bin/env python3
"""追蹤價格（其他）比價網站產生器（架構比照貓品比價站 cat-food-prices）。

讀取價格追蹤資料（~/workspace/price-tracker-handoff/<slug>/prices.csv 與
platforms.json，唯讀），產生本站根目錄的靜態網站：
  index.html   （內嵌同一份資料，首屏無需額外請求）
  data.json    （同一份資料，方便除錯或其他用途）
  assets/      （style.css、app.js，由 web/ 複製）
  favicon 等圖示（由 web/icons/ 複製）

GitHub Pages 設定為 main 分支根目錄（/），所以輸出固定在 repo 根目錄，
不使用 docs/ 資料夾。商品圖在 images/<slug>.jpg（自行託管，不外連）。

用法： python3 build.py
每日流程：改 handoff 的 prices.csv → python3 build.py → 上傳 index.html、
data.json（以及有變動的 assets/、images/）到 repo 根目錄。
"""
import csv
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
TZ = ZoneInfo("Europe/Amsterdam")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ── 可買判斷（CSV 沒有庫存欄，庫存／寄送狀態寫在 note 自由文字裡）──────────
# 不寄荷蘭的平台（platforms.json／官網條款已查證）：在 site.config.json 的
# products.<slug>.blocked_platforms 設定，{平台名: 原因}，直接排除於最佳價。
# 其餘以 note 文字判斷：先看負面訊號（缺貨、售罄、僅到貨通知…），
# 若同時有正面訊號（有貨、現貨、可訂…，且不是「無貨」「不可訂」的子字串）
# 則以正面為準（同一列常會提到其他規格缺貨）。
NEG_MARKERS = [
    "缺貨", "無貨", "售罄", "僅到貨通知", "無購物車", "不可訂", "404",
    "下架", "未販售", "無此商品", "搜尋0結果", "搜尋 0 結果", "按鈕停用",
    "uitverkocht", "niet leverbaar", "niet op voorraad", "out of stock",
    "nicht auf lager",
]
POS_PATTERNS = [
    r"(?<!無)有貨(?!時)", r"(?<!無)現貨", r"(?<!不)可訂", r"可加購物車",
    r"(?<!無)有庫存", r"已訂", r"到貨窗", r"預計[^；]*到貨", r"可送荷蘭",
    r"op voorraad", r"in stock",
]


def is_date(v):
    return bool(v and DATE_RE.match(v.strip()))


def is_verified(row):
    return row["verified"].lower().startswith("yes")


def num(v):
    try:
        return None if v is None or str(v).strip() == "" else float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def read_rows(slug, src_dir):
    """讀 prices.csv 並正規化欄位。兩種版式：
    標準：group,date,platform,seller,variant,url,price,shipping,threshold,
          promo,cashback_pct,cashback_eur,net_total,verified,note
    舊版（2026-11-10 列，無 group／url）：
          platform,seller,date,variant,price,shipping,threshold,promo,
          cashback_pct,cashback_eur,net_total,verified,note
    """
    path = src_dir / slug / "prices.csv"
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        for raw in reader:
            if not raw or all(not c.strip() for c in raw):
                continue
            if len(raw) >= 3 and is_date(raw[2]) and not is_date(raw[1]):
                keys = ["platform", "seller", "date", "variant", "price",
                        "shipping", "threshold", "promo", "cashback_pct",
                        "cashback_eur", "net_total", "verified", "note"]
                row = dict(zip(keys, raw))
                row.setdefault("url", "")
                row.setdefault("group", "")
            else:
                row = dict(zip(header, raw))
            rows.append({k: (row.get(k) or "").strip() for k in (
                "date", "platform", "seller", "variant", "url", "price",
                "shipping", "threshold", "promo", "cashback_pct",
                "cashback_eur", "net_total", "verified", "note")})
    return rows


def read_platforms(slug, src_dir):
    path = src_dir / slug / "platforms.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def blocked_reason(row, blocked):
    for name, reason in (blocked or {}).items():
        if name and (name == row["platform"] or name in row["platform"] or row["platform"] in name):
            return reason
    return None


def assess(row, blocked):
    """回傳 (purchasable, blocked_reason)。
    purchasable＝已核實、有淨價、未被平台封鎖、且 note 未顯示缺貨
    （或同時有正面有貨訊號）。比照貓站 best 只計 in_stock+verified 的邏輯。"""
    reason = blocked_reason(row, blocked)
    if reason:
        return False, reason
    if not is_verified(row) or num(row["net_total"]) is None:
        return False, None
    text = row["note"]
    low = text.lower()
    neg = any(m in low for m in NEG_MARKERS)
    if not neg:
        return True, None
    pos = any(re.search(p, text) for p in POS_PATTERNS)
    return pos, None


def shipping_label(shipping):
    s = (shipping or "").strip()
    if not s:
        return ""
    if s == "0":
        return "免運"
    v = num(s)
    if v is not None:
        return "免運" if v == 0 else f"運費 €{v:.2f}"
    return s


def offer_tags(row, aliases):
    tags = []
    sl = shipping_label(row["shipping"])
    if sl:
        tags.append({"k": "ship", "t": sl})
    th = (row["threshold"] or "").strip()
    if th and th != sl and th != (row["shipping"] or "").strip():
        tags.append({"k": "cond", "t": th})
    promo = (row["promo"] or "").strip()
    if promo and promo != "無":
        tags.append({"k": "deal", "t": promo})
    cb_eur = num(row["cashback_eur"])
    m = re.search(r"([\d.]+)\s*%\s*([^（(]*)", row["cashback_pct"] or "")
    if m and cb_eur:
        portal = m.group(2).strip()
        portal = aliases.get(portal, portal)
        tag = {"k": "cash", "t": (f"{portal} 返現約 €{cb_eur:.2f}" if portal else f"返現約 €{cb_eur:.2f}")}
        if portal:
            tag["p"] = portal
        tags.append(tag)
    return tags


def offer_view(row, blocked, aliases):
    purchasable, breason = assess(row, blocked)
    if breason:
        status = breason
    elif not is_verified(row):
        status = "未核實"
    elif num(row["net_total"]) is None:
        status = "無報價"
    elif not purchasable:
        status = "缺貨／不可訂"
    else:
        status = ""
    return {
        "shop": row["platform"],
        "seller": row["seller"],
        "variant": row["variant"],
        "date": row["date"],
        "url": row["url"] if row["url"].startswith(("http://", "https://")) else "",
        "price": num(row["price"]),
        "shipping": row["shipping"],
        "shipping_label": shipping_label(row["shipping"]),
        "net": num(row["net_total"]),
        "verified": is_verified(row),
        "verified_text": row["verified"],
        "note": row["note"],
        "tags": offer_tags(row, aliases),
        "purchasable": purchasable,
        "blocked_reason": breason or "",
        "status_text": status,
        "carried": False,
    }


# ── 價格水準／徽章（移植自貓站 build.py 的 price_level／price_drop）────────
LEVEL_MIN_POINTS = 7
LEVEL_WINDOW_DAYS = 90


def percentile(vals, q):
    v = sorted(vals)
    if not v:
        return None
    i = (len(v) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def price_level(hist, cur, cur_date):
    """依該商品自己的「每日最低可買淨價」歷史判斷今日偏低／一般／偏高。"""
    if cur is None or not cur_date:
        return None
    start = (dt.date.fromisoformat(cur_date) - dt.timedelta(days=LEVEL_WINDOW_DAYS)).isoformat()
    vals = [h["net"] for h in hist if h.get("net") is not None and start < h["date"] <= cur_date]
    n = len(vals)
    if n < LEVEL_MIN_POINTS:
        return {"status": "collecting", "n": n, "need": LEVEL_MIN_POINTS}
    p25, p75 = percentile(vals, .25), percentile(vals, .75)
    lo, hi = min(vals), max(vals)
    tol = max(1e-6, lo * 0.005)
    if hi - lo <= tol:
        level = "typical"
    elif cur <= lo + tol:
        level = "low"
    elif cur >= hi - tol:
        level = "high"
    elif p75 - p25 <= max(1e-6, p25 * 0.005):
        level = "typical"
    elif cur <= p25 + 1e-6:
        level = "low"
    elif cur >= p75 - 1e-6:
        level = "high"
    else:
        level = "typical"
    r = lambda x: round(x, 2)
    return {"status": "ok", "n": n, "level": level, "cur": r(cur),
            "min": r(lo), "p25": r(p25), "p75": r(p75), "max": r(hi)}


def price_drop(hist, cur, cur_date, days=30):
    """降價幅度（%）：目前價比過去 days 天（不含今天）每日最低價的最高點低多少。"""
    if cur is None or not cur_date:
        return 0.0
    start = (dt.date.fromisoformat(cur_date) - dt.timedelta(days=days)).isoformat()
    prev = [h["net"] for h in hist if start <= h["date"] < cur_date and h.get("net")]
    if not prev:
        return 0.0
    ref = max(prev)
    return round(max(0.0, (ref - cur) / ref * 100), 1)


def fmt_date_zh(d):
    return f"{d.year}年{d.month}月{d.day}日"


def build():
    cfg = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
    src_dir = Path(cfg.get("source_dir") or ROOT.parent / "price-tracker-handoff")
    aliases = cfg.get("cashback_portal_aliases") or {}

    # 商品清單：設定檔順序優先，handoff 有而設定沒寫的自動附加
    # （exclude_products 與 *-archived 資料夾除外，例如已停追的 newtral-chair）
    excluded = set(cfg.get("exclude_products") or [])
    pids = [p for p in cfg.get("product_order", []) if p not in excluded]
    if src_dir.exists():
        for d in sorted(src_dir.iterdir()):
            if (d / "prices.csv").exists() and d.name not in pids \
                    and d.name not in excluded and not d.name.endswith("archived"):
                pids.append(d.name)

    products = []
    unverified_all = []
    total_rows = 0
    latest_all = ""
    for pid in pids:
        meta = (cfg.get("products") or {}).get(pid, {})
        rows = read_rows(pid, src_dir)
        pdata = read_platforms(pid, src_dir)
        total_rows += len(rows)
        blocked = meta.get("blocked_platforms") or {}
        views = [offer_view(r, blocked, aliases) for r in rows]
        dated = [v for v in views if is_date(v["date"])]
        if not dated:
            continue
        dates = sorted({v["date"] for v in dated})
        cur_date = dates[-1]
        latest_all = max(latest_all, cur_date)

        # 目前報價：最新查價日的列 + 補回（carried）先前查過、今天未重查的
        # （平台，賣家）最近一筆，標 carried、不參與最佳價（比照貓站規則）。
        cur = [v for v in dated if v["date"] == cur_date]
        cur_keys = {(v["shop"], v["seller"]) for v in cur}
        latest_by_key = {}
        for v in dated:
            if v["date"] == cur_date:
                continue
            k = (v["shop"], v["seller"])
            if k in cur_keys:
                continue
            if k not in latest_by_key or v["date"] >= latest_by_key[k]["date"]:
                latest_by_key[k] = v
        for v in latest_by_key.values():
            v = dict(v)
            v["carried"] = True
            cur.append(v)
        main = [v for v in cur if v["purchasable"] and not v["carried"]]
        main.sort(key=lambda v: v["net"])
        others = [v for v in cur if not (v["purchasable"] and not v["carried"])]
        others.sort(key=lambda v: v["net"] if v["net"] is not None else float("inf"))
        others.sort(key=lambda v: v["date"], reverse=True)  # 穩定排序：日期新到舊，同日淨價低到高
        offers = main + others
        best = main[0] if main else None

        # 價格歷史：每日最低可買淨價
        hist = []
        for d in dates:
            day = [v for v in dated if v["date"] == d and v["purchasable"]]
            if day:
                hist.append({"date": d, "net": round(min(v["net"] for v in day), 2)})

        # 新低價徽章（比照貓站）
        badge = None
        if best:
            prev = [h["net"] for h in hist if h["date"] < cur_date]
            prev_min = min(prev) if prev else None
            if prev_min is None:
                badge = {"kind": "first", "text": "首次紀錄"}
            elif best["net"] < prev_min - 1e-6:
                badge = {"kind": "new_low", "text": "新低價", "prev": prev_min}
            elif abs(best["net"] - prev_min) <= 1e-6:
                badge = {"kind": "at_low", "text": "持平歷史低價"}
            else:
                pct = (best["net"] / prev_min - 1) * 100
                badge = {"kind": "above", "text": f"比歷史低價高 {pct:.0f}%", "prev": prev_min}

        img = meta.get("image") or f"images/{pid}.jpg"
        if not (ROOT / img).exists():
            print(f"警告：{pid} 沒有商品圖片（{img}）", file=sys.stderr)
            img = None

        # 全部紀錄表：日期新到舊，同日維持檔案順序
        all_rows = sorted(enumerate(views),
                          key=lambda t: (t[1]["date"] or "", -t[0]), reverse=True)
        all_rows = [v for _, v in all_rows]

        for u in pdata.get("unverified") or []:
            unverified_all.append({
                "product": meta.get("name") or pid,
                "site": u.get("site", ""),
                "reason": u.get("reason", ""),
            })

        products.append({
            "id": pid,
            "brand": meta.get("brand", ""),
            "name": meta.get("name") or pdata.get("product") or pid,
            "desc": meta.get("desc") or pdata.get("product") or "",
            "image": img,
            "date": cur_date,
            "best": best,
            "badge": badge,
            "level": price_level(hist, best["net"] if best else None, cur_date),
            "drop": price_drop(hist, best["net"] if best else None, cur_date),
            "history": hist,
            "offers": offers,
            "rows": all_rows,
            "record_count": len(rows),
            "shop_count": len({v["shop"] for v in main}),
            "main_count": len(main),
        })

    # 返現邀請：只列目前報價實際用到的返現網站（比照貓站 cashback_invites）
    used = set()
    for p in products:
        for o in p["offers"]:
            for t in o["tags"]:
                if t.get("k") == "cash" and t.get("p"):
                    used.add(t["p"])
    invites = []
    for name, url in (cfg.get("cashback_invites") or {}).items():
        if name in used and (url or "").strip():
            invites.append({"name": name, "url": url.strip(),
                            "note": ((cfg.get("cashback_invite_notes") or {}).get(name) or "").strip()})

    now = dt.datetime.now(TZ)
    upd = dt.date.fromisoformat(latest_all) if latest_all else now.date()
    nxt = upd + dt.timedelta(days=cfg.get("update_interval_days", 1))
    site = {
        "title": cfg.get("site_title", "追蹤價格（其他）"),
        "site_sub": cfg.get("site_sub", ""),
        "updated": latest_all,
        "updated_zh": fmt_date_zh(upd),
        "next": nxt.isoformat(),
        "next_zh": f"{nxt.month}月{nxt.day}日",
        "generated_zh": now.strftime("%Y-%m-%d %H:%M"),
        "location": "鹿特丹",
        "products": products,
        "cashback_invites": invites,
        "details": {
            "assumptions": cfg.get("assumptions", ""),
            "unverified": unverified_all,
        },
    }
    js = json.dumps(site, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "data.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "assets").mkdir(exist_ok=True)
    for f in ("style.css", "app.js"):
        shutil.copy2(WEB / f, ROOT / "assets" / f)
    for f in (WEB / "icons").iterdir():
        shutil.copy2(f, ROOT / f.name)
    ver = now.strftime("%Y%m%d%H%M")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace("__DATA__", js.replace("</", "<\\/")).replace("__VER__", ver)
    html = html.replace("__TITLE__", site["title"]).replace("__UPDATED__", site["updated_zh"])
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    (ROOT / ".nojekyll").write_text("")
    # 舊版每商品一頁的產出已被單頁版取代，清掉避免誤傳舊頁
    for p in products:
        stale = ROOT / f"{p['id']}.html"
        if stale.exists():
            stale.unlink()
            print(f"刪除舊版商品頁：{stale.name}")
    print(f"完成：{len(products)} 項商品、共 {total_rows} 筆紀錄，資料日期 {latest_all}，輸出 {ROOT}")
    for p in products:
        b = p["best"]
        print(f"  {p['id']}: {p['record_count']} 筆，最佳價 " +
              (f"€{b['net']:.2f} @{b['shop']}" if b else "（無已核實可買價）"))


if __name__ == "__main__":
    build()
