#!/usr/bin/env python3
"""
Builds the Phase 1 manifest for all 41 Grand Canal Boats from raw_archive/cat32.html
and raw_archive/cdx/cdx_html.json.
"""
import json
import re
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
CAT32_PATH = BASE_DIR / "raw_archive" / "cat32.html"
CDX_HTML_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_html.json"
MANIFEST_PATH = BASE_DIR / "raw_archive" / "phase1_manifest.json"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def main():
    with open(CDX_HTML_PATH, "r", encoding="utf-8") as f:
        cdx_rows = json.load(f)[1:]

    # Map article id -> best (timestamp, original_url) for main view and pop=1 fallback
    main_snapshots = {}
    pop_snapshots = {}
    for row in cdx_rows:
        ts, orig_url = row[1], row[2]
        if "/cms/" in orig_url and "task=view" in orig_url and "Itemid=64" in orig_url:
            clean_url = orig_url.replace("&amp;", "&")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(clean_url).query)
            aid = qs.get("id", [""])[0].strip()
            if not aid.isdigit():
                continue
            aid_int = int(aid)
            if "index2.php" in clean_url or "pop=1" in clean_url:
                pop_snapshots[aid_int] = (ts, clean_url)
            else:
                # Prefer 2017+ snapshot if multiple exist
                if aid_int not in main_snapshots or ts > main_snapshots[aid_int][0]:
                    main_snapshots[aid_int] = (ts, clean_url)

    html = CAT32_PATH.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    vessels = []
    for tr in soup.select("tr.sectiontableentry1, tr.sectiontableentry2"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        date_str = tds[0].get_text(strip=True)
        link = tds[1].find("a")
        if not link:
            continue
        title = " ".join(link.get_text().split())
        href = link.get("href", "").replace("&amp;", "&")
        hits_str = tds[2].get_text(strip=True)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        aid = int(qs["id"][0])

        ts, snap_url = main_snapshots.get(aid, (None, href))
        pop_ts, pop_url = pop_snapshots.get(aid, (None, None))

        # Extract boat registration prefix (e.g., 61M, 32E)
        reg_match = re.match(r"^([0-9]+[A-Z]+)", title)
        reg_num = reg_match.group(1) if reg_match else title.split()[0]

        vessels.append({
            "article_id": aid,
            "reg_number": reg_num,
            "title": title,
            "slug": slugify(title.split(" - GCC")[0]),
            "listed_date": date_str,
            "hits": int(hits_str) if hits_str.isdigit() else 0,
            "original_url": snap_url,
            "wayback_timestamp": ts,
            "wayback_raw_url": f"https://web.archive.org/web/{ts}id_/{snap_url}" if ts else None,
            "wayback_public_url": f"https://web.archive.org/web/{ts}/{snap_url}" if ts else None,
            "fallback_pop_timestamp": pop_ts,
            "fallback_pop_raw_url": f"https://web.archive.org/web/{pop_ts}id_/{pop_url}" if pop_ts else None,
            "local_html_file": f"raw_archive/cms_articles/item_64_id_{aid}.html",
        })

    # Sort by boat registration number
    vessels.sort(key=lambda v: (int(re.sub(r"[^0-9]", "", v["reg_number"]) or 0), v["reg_number"]))

    MANIFEST_PATH.write_text(json.dumps(vessels, indent=2), encoding="utf-8")
    print(f"Created Phase 1 manifest with {len(vessels)} Grand Canal Boats at {MANIFEST_PATH}")
    missing_ts = [v for v in vessels if not v["wayback_timestamp"]]
    print(f"Missing Wayback timestamps: {len(missing_ts)}")
    for v in vessels[:5]:
        print(f"  {v['reg_number']:4s} | id={v['article_id']:3d} | ts={v['wayback_timestamp']} | {v['title']}")


if __name__ == "__main__":
    main()
