#!/usr/bin/env python3
"""Regenerate the static price-comparison site from the price-tracker CSVs.

Reads only:
  ~/workspace/price-tracker-handoff/<slug>/prices.csv
  ~/workspace/price-tracker-handoff/<slug>/platforms.json

Writes plain static HTML into this directory (index.html + one page per
product). No dependencies beyond the Python 3 standard library.
Running it is idempotent: output depends only on the CSV contents.

Usage:  python3 build.py
"""
import csv
import html
import json
import re
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
HANDOFF_DIR = SITE_DIR.parent / "price-tracker-handoff"

PRODUCTS = [
    ("levoit-core-400s", "Levoit Core 400S"),
    ("philips-ac3033", "Philips AC3033/10"),
    ("winix-zero-s", "Winix Zero S"),
    ("philips-ac4221", "Philips Pro 4200 AC4221/11"),
    ("iqair-healthpro-250", "IQAir HealthPro 250"),
    ("levoit-core-600s", "Levoit Core 600S"),
]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI",Roboto,"Noto Sans TC",sans-serif;margin:0;padding:16px;line-height:1.55;background:#f6f7f9;color:#1a1d21}
@media (prefers-color-scheme:dark){body{background:#14171a;color:#e8eaed}}
main{max-width:1080px;margin:0 auto}
h1{font-size:1.6rem;margin:.2em 0}
h2{font-size:1.15rem}
a{color:#0b5cad}
.meta{color:#666;font-size:.9rem}
@media (prefers-color-scheme:dark){.meta{color:#9aa0a6}}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:16px}
.card{background:#fff;border:1px solid #dde1e6;border-radius:10px;padding:14px 16px}
@media (prefers-color-scheme:dark){.card{background:#1e2226;border-color:#33383e}}
.card h2{margin:.1em 0 .3em}
.card .price{font-size:1.25rem;font-weight:700}
.card .sub{color:#666;font-size:.85rem;word-break:break-word}
@media (prefers-color-scheme:dark){.card .sub{color:#9aa0a6}}
.tablewrap{overflow-x:auto;background:#fff;border:1px solid #dde1e6;border-radius:10px}
@media (prefers-color-scheme:dark){.tablewrap{background:#1e2226;border-color:#33383e}}
table{border-collapse:collapse;width:100%;font-size:.88rem;min-width:860px}
th,td{border-bottom:1px solid #e3e6ea;padding:7px 9px;text-align:left;vertical-align:top}
@media (prefers-color-scheme:dark){th,td{border-color:#2c3138}}
th{background:#eef1f4;white-space:nowrap}
@media (prefers-color-scheme:dark){th{background:#262b31}}
td.num{white-space:nowrap;text-align:right}
td.date{white-space:nowrap}
.badge{display:inline-block;padding:0 .45em;border-radius:1em;font-size:.78rem;white-space:nowrap}
.ok{background:#e2f2e4;color:#145c1e}
.no{background:#fbe4e4;color:#8c1d1d}
@media (prefers-color-scheme:dark){.ok{background:#173d1e;color:#8fd694}.no{background:#4a1d1d;color:#f0a3a3}}
tr.unverified td{opacity:.75}
.note{font-size:.82rem}
footer{margin-top:20px;color:#666;font-size:.85rem}
@media (prefers-color-scheme:dark){footer{color:#9aa0a6}}
"""


def is_date(value):
    return bool(value and DATE_RE.match(value.strip()))


def read_rows(slug):
    """Return normalised rows from prices.csv.

    Most rows follow the header layout
    group,date,platform,seller,variant,url,price,shipping,threshold,promo,
    cashback_pct,cashback_eur,net_total,verified,note
    A few legacy rows (2026-11-10) use a shorter layout without group/url:
    platform,seller,date,variant,price,shipping,threshold,promo,
    cashback_pct,cashback_eur,net_total,verified,note
    Both are normalised to the same dict keys.
    """
    path = HANDOFF_DIR / slug / "prices.csv"
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        for raw in reader:
            if not raw or all(not c.strip() for c in raw):
                continue
            if len(raw) >= 3 and is_date(raw[2]) and not is_date(raw[1]):
                # legacy layout
                keys = ["platform", "seller", "date", "variant", "price",
                        "shipping", "threshold", "promo", "cashback_pct",
                        "cashback_eur", "net_total", "verified", "note"]
                row = dict(zip(keys, raw))
                row.setdefault("url", "")
                row.setdefault("group", "")
            else:
                row = dict(zip(header, raw))
            rows.append({
                "date": (row.get("date") or "").strip(),
                "platform": (row.get("platform") or "").strip(),
                "seller": (row.get("seller") or "").strip(),
                "variant": (row.get("variant") or "").strip(),
                "url": (row.get("url") or "").strip(),
                "price": (row.get("price") or "").strip(),
                "shipping": (row.get("shipping") or "").strip(),
                "net_total": (row.get("net_total") or "").strip(),
                "verified": (row.get("verified") or "").strip(),
                "note": (row.get("note") or "").strip(),
            })
    return rows


def read_product_desc(slug):
    path = HANDOFF_DIR / slug / "platforms.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return (data.get("product") or "").strip()


def is_verified(row):
    return row["verified"].lower().startswith("yes")


def parse_price(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fmt_eur(value):
    num = parse_price(value)
    if num is None:
        return html.escape(value) if value else "—"
    return "€" + f"{num:,.2f}"


def latest_summary(rows):
    """Latest verified priced row: prefer the newest date, then cheapest net."""
    dated = [r for r in rows if is_date(r["date"])]
    if not dated:
        return None
    newest = max(r["date"] for r in dated)
    for cutoff in sorted({r["date"] for r in dated}, reverse=True):
        cand = [r for r in dated
                if r["date"] == cutoff and is_verified(r)
                and parse_price(r["net_total"]) is not None]
        if cand:
            best = min(cand, key=lambda r: parse_price(r["net_total"]))
            return {"date": newest, "price_date": cutoff, "row": best}
    return {"date": newest, "price_date": None, "row": None}


def page_shell(title, body):
    return ("<!DOCTYPE html>\n<html lang=\"zh-Hant\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{html.escape(title)}</title>\n"
            f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n"
            "</main>\n</body>\n</html>\n")


def build_product_page(slug, name, desc, rows, last_updated):
    trs = []
    for r in rows:
        verified = is_verified(r)
        badge = ('<span class="badge ok">已核實</span>' if verified
                 else '<span class="badge no">未核實</span>')
        ver_text = html.escape(r["verified"])
        platform = html.escape(r["platform"]) or "—"
        if r["url"].startswith(("http://", "https://")):
            platform = (f'<a href="{html.escape(r["url"], quote=True)}" '
                        f'target="_blank" rel="noopener">{platform}</a>')
        trs.append(
            f'<tr class="{"unverified" if not verified else ""}">'
            f'<td class="date">{html.escape(r["date"])}</td>'
            f"<td>{platform}</td>"
            f'<td>{html.escape(r["seller"]) or "—"}</td>'
            f'<td>{html.escape(r["variant"]) or "—"}</td>'
            f'<td class="num">{fmt_eur(r["price"])}</td>'
            f'<td>{html.escape(r["shipping"]) or "—"}</td>'
            f'<td class="num">{fmt_eur(r["net_total"])}</td>'
            f"<td>{badge}<br><span class=\"note\">{ver_text}</span></td>"
            f'<td class="note">{html.escape(r["note"])}</td>'
            "</tr>")
    body = (
        '<p><a href="index.html">← 回總覽</a></p>\n'
        f"<h1>{html.escape(name)}</h1>\n"
        f'<p class="meta">{html.escape(desc)}</p>\n'
        f'<p class="meta">最後更新：{last_updated}・共 {len(rows)} 筆查價紀錄'
        "（日期為每筆實際查價日，未核實列已標示）</p>\n"
        '<div class="tablewrap"><table>\n<thead><tr>'
        "<th>日期</th><th>平台</th><th>賣家</th><th>規格</th><th>價格</th>"
        "<th>運費</th><th>淨總價</th><th>核實</th><th>備註</th>"
        "</tr></thead>\n<tbody>\n" + "\n".join(trs) + "\n</tbody></table></div>\n"
        "<footer>價格單位 EUR。未核實列為比價站刊載或當日無法開頁確認，"
        "不可當現價。</footer>")
    return page_shell(f"{name}｜追蹤價格（其他）", body)


def build_index(cards, last_updated):
    card_html = []
    for slug, name, desc, summary, count in cards:
        if summary and summary["row"]:
            r = summary["row"]
            price_line = (f'<p class="price">{fmt_eur(r["net_total"])}'
                          f' <span class="sub">@{html.escape(r["platform"])}'
                          f'（{summary["price_date"]} 已核實）</span></p>')
        else:
            price_line = '<p class="price">暫無已核實價格</p>'
        card_html.append(
            '<section class="card">'
            f'<h2><a href="{slug}.html">{html.escape(name)}</a></h2>'
            f'<p class="sub">{html.escape(desc)}</p>'
            f"{price_line}"
            f'<p class="sub">最後查價：{summary["date"] if summary else "—"}'
            f'・共 {count} 筆紀錄</p>'
            f'<p><a href="{slug}.html">看全部查價紀錄 →</a></p>'
            "</section>")
    body = (
        "<h1>追蹤價格（其他）</h1>\n"
        f'<p class="meta">最後更新：{last_updated}・追蹤 6 款空氣清淨機在'
        "可寄荷蘭鹿特丹的各平台價格與庫存。只讀查價，不代下單。</p>\n"
        '<div class="cards">\n' + "\n".join(card_html) + "\n</div>\n"
        "<footer>價格單位 EUR。未核實價格已在各商品頁標示，不可當現價。"
        "本頁由 build.py 依每日查價 CSV 自動產生。</footer>")
    return page_shell("追蹤價格（其他）", body)


def main():
    all_data = []
    last_updated = ""
    for slug, name in PRODUCTS:
        rows = read_rows(slug)
        desc = read_product_desc(slug)
        for r in rows:
            if is_date(r["date"]):
                last_updated = max(last_updated, r["date"])
        all_data.append((slug, name, desc, rows))
    cards = []
    for slug, name, desc, rows in all_data:
        (SITE_DIR / f"{slug}.html").write_text(
            build_product_page(slug, name, desc, rows, last_updated),
            encoding="utf-8")
        cards.append((slug, name, desc, latest_summary(rows), len(rows)))
    (SITE_DIR / "index.html").write_text(
        build_index(cards, last_updated), encoding="utf-8")
    print(f"last_updated={last_updated}")
    for slug, name, desc, rows in all_data:
        print(f"{slug}: {len(rows)} rows -> {slug}.html")
    print("index.html written")


if __name__ == "__main__":
    main()
