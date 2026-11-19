#!/usr/bin/env python3
"""
Phase 2 & Phase 3 Downloader:
1. Downloads all 10 remaining Joomla Vessel Category index pages (sectionid=4, Itemid=64)
2. Downloads all 64 remaining Joomla Vessel/Boatyard/Photo articles (+ multi-page continuations)
3. Downloads all 77 Static HTML pages (2004-2007 era: /*.htm and /HBASiteSpring2007/*.htm)
4. Downloads all 30 WordPress Vessel & Essential Grid pages (2020-2026 era)
5. Extracts and downloads all images referenced across these pages from the CDX asset index.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
CDX_HTML_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_html.json"
CDX_ASSETS_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_assets.json"
PHASE1_MANIFEST = BASE_DIR / "raw_archive" / "phase1_manifest.json"

CMS_CAT_DIR = BASE_DIR / "raw_archive" / "cms_categories"
CMS_ART_DIR = BASE_DIR / "raw_archive" / "cms_articles"
STATIC_DIR = BASE_DIR / "raw_archive" / "static_2004_2007"
WP_DIR = BASE_DIR / "raw_archive" / "wp_2020_2026"
IMG_OUT_DIR = BASE_DIR / "content" / "images" / "vessels"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HBA-Archival-Preservation/1.0"
}


def fetch_url(url: str, max_retries: int = 4, base_delay: float = 3.0) -> bytes:
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504):
                wait = base_delay * (2 ** attempt) + 5.0
                print(f"  [HTTP {e.code}] Rate limited/busy on {url}, waiting {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            wait = base_delay * (2 ** attempt) + 2.0
            print(f"  [Error: {e}] Retrying in {wait:.1f}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


def clean_filename(norm_path: str) -> str:
    rel = norm_path
    for prefix in ["/cms/images/stories/", "/cms/images/", "/images/", "/hbasitespring2007/"]:
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    p = Path(rel)
    ext = p.suffix.lower() or ".jpg"
    stem = str(p.with_suffix(""))
    clean_stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{clean_stem}{ext}"


def extract_imgs_from_html(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    main_div = soup.select_one("div.main-left-only") or soup
    srcs = []
    for img in main_div.find_all("img"):
        src = img.get("src", "").strip()
        if not src or any(x in src for x in ["pdf_button", "printButton", "emailButton", "arrow.png", "logo.png", "weblink.png", "con_info.png"]):
            continue
        srcs.append(src)
    return srcs


def main():
    for d in [CMS_CAT_DIR, CMS_ART_DIR, STATIC_DIR, WP_DIR, IMG_OUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    cdx_html = json.loads(CDX_HTML_PATH.read_text(encoding="utf-8"))[1:]
    phase1_ids = {v["article_id"] for v in json.loads(PHASE1_MANIFEST.read_text(encoding="utf-8"))}

    # 1. Download all 10 remaining Joomla Category Index pages (sectionid=4, Itemid=64)
    cats = [
        (33, "Bye-Trader Boats", "20171029085652", True),
        (34, "Royal Canal Floats", "20171029085654", False),
        (35, "Steam Boats", "20171029085706", False),
        (36, "Wooden Barges and Boats", "20171029085717", False),
        (41, "Horse Boats", "20171029085724", False),
        (37, "Dutch Motor and Sailing Barges", "20171029085732", False),
        (38, "Other Vessels", "20171029085740", False),
        (39, "Modern Barges and Boats", "20171029085749", False),
        (40, "Boatyards, Boatbuilders and Engines", "20171029085758", False),
        (42, "Boat Photos", "20171029085625", False),
    ]
    print("=== Step 1: Downloading 10 Joomla Vessel Category Index Pages ===")
    for cid, name, ts, add_limit in cats:
        out_f = CMS_CAT_DIR / f"cat_{cid}.html"
        if out_f.exists() and out_f.stat().st_size > 500:
            print(f"  Category {cid} ({name}) already cached")
            continue
        u = f"https://web.archive.org/web/{ts}id_/http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=4&id={cid}&Itemid=64"
        if add_limit:
            u += "&limit="
        print(f"  Fetching Category {cid} ({name})...")
        raw = fetch_url(u)
        out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        time.sleep(2.5)

    # 2. Download all 64 remaining Itemid=64 articles (+ multi-page continuations)
    print("\n=== Step 2: Downloading 64 Remaining Joomla Itemid=64 Articles ===")
    item64_main = {}
    item64_pop = {}
    item64_pages = []
    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        if "/cms/" in orig_url and "task=view" in orig_url and "Itemid=64" in orig_url:
            u = orig_url.replace("&amp;", "&")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            aid = qs.get("id", [""])[0].strip()
            if not aid.isdigit() or int(aid) in phase1_ids:
                continue
            aid_int = int(aid)
            if "index2.php" in u or "pop=1" in u:
                item64_pop[aid_int] = (ts, u)
            elif "limitstart=1" in u:
                item64_pages.append((aid_int, 2, ts, u))
            else:
                if aid_int not in item64_main or ts > item64_main[aid_int][0]:
                    item64_main[aid_int] = (ts, u)

    sorted_aids = sorted(item64_main.keys())
    for idx, aid in enumerate(sorted_aids, 1):
        out_f = CMS_ART_DIR / f"item_64_id_{aid}.html"
        if out_f.exists() and out_f.stat().st_size > 500:
            continue
        ts, u = item64_main[aid]
        wb_u = f"https://web.archive.org/web/{ts}id_/{u}"
        print(f"  [{idx:2d}/{len(sorted_aids)}] Fetching id={aid} from {wb_u}...")
        try:
            raw = fetch_url(wb_u)
        except Exception:
            if aid in item64_pop:
                pts, pu = item64_pop[aid]
                raw = fetch_url(f"https://web.archive.org/web/{pts}id_/{pu}")
            else:
                raise
        out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        time.sleep(2.5)

    for aid, pnum, ts, u in item64_pages:
        out_f = CMS_ART_DIR / f"item_64_id_{aid}_page{pnum}.html"
        if not out_f.exists() or out_f.stat().st_size < 500:
            print(f"  Fetching id={aid} page {pnum}...")
            raw = fetch_url(f"https://web.archive.org/web/{ts}id_/{u}")
            out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
            time.sleep(2.5)

    # 3. Download all 77 Static 2004-2007 HTML pages
    print("\n=== Step 3: Downloading All 77 Static 2004-2007 HTML Pages ===")
    static_pages = []
    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        path = urllib.parse.urlparse(orig_url).path
        if (path.endswith((".htm", ".html")) or path.endswith("/HBASiteSpring2007/")) and "/cms/" not in path:
            static_pages.append((ts, orig_url, path))

    for idx, (ts, orig_url, path) in enumerate(static_pages, 1):
        rel_name = path.lstrip("/").replace("/", "__") or "root_index.htm"
        if not rel_name.endswith((".htm", ".html")):
            rel_name = rel_name.rstrip("_") + "__index.htm"
        out_f = STATIC_DIR / rel_name
        if out_f.exists() and out_f.stat().st_size > 200:
            continue
        wb_u = f"https://web.archive.org/web/{ts}id_/{orig_url}"
        print(f"  [{idx:2d}/{len(static_pages)}] Fetching static {rel_name} ({ts})...")
        raw = fetch_url(wb_u)
        out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        time.sleep(2.0)

    # 4. Download WordPress 2020-2026 Vessel & Essential Grid pages
    print("\n=== Step 4: Downloading WordPress 2020-2026 Vessel & Grid Pages ===")
    wp_pages = []
    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        path = urllib.parse.urlparse(orig_url).path
        if "/cms/" not in path and not path.endswith((".htm", ".html")):
            if any(k in path.lower() for k in ["/vessels", "/essential_grid", "/uk-vessels", "bolinder-engine"]):
                wp_pages.append((ts, orig_url, path))

    for idx, (ts, orig_url, path) in enumerate(wp_pages, 1):
        slug_name = path.strip("/").replace("/", "__") or "wp_root"
        out_f = WP_DIR / f"{slug_name}.html"
        if out_f.exists() and out_f.stat().st_size > 500:
            continue
        wb_u = f"https://web.archive.org/web/{ts}id_/{orig_url}"
        print(f"  [{idx:2d}/{len(wp_pages)}] Fetching WP {slug_name} ({ts})...")
        raw = fetch_url(wb_u)
        out_f.write_text(raw.decode("utf-8", errors="replace"), encoding="utf-8")
        time.sleep(2.0)

    # 5. Discover and download all images referenced in Phase 2 & 3 HTML files
    print("\n=== Step 5: Discovering & Downloading Phase 2 & 3 Images ===")
    cdx_assets = json.loads(CDX_ASSETS_PATH.read_text(encoding="utf-8"))[1:]
    asset_map = {}
    basename_map = {}
    for row in cdx_assets:
        ts, orig_url, mime, status = row[1], row[2], row[3], row[4]
        parsed = urllib.parse.urlparse(orig_url)
        norm_path = urllib.parse.unquote(parsed.path).lower().replace("//", "/")
        if norm_path not in asset_map or ts > asset_map[norm_path][0]:
            asset_map[norm_path] = (ts, orig_url, mime)
        bname = Path(norm_path).name
        if bname and (bname not in basename_map or ts > basename_map[bname][0]):
            basename_map[bname] = (ts, orig_url, mime, norm_path)

    all_srcs = []
    for folder in [CMS_CAT_DIR, CMS_ART_DIR, STATIC_DIR]:
        for hf in folder.glob("*.htm*"):
            all_srcs.extend(extract_imgs_from_html(hf.read_text(encoding="utf-8", errors="replace")))

    media_map_path = BASE_DIR / "data" / "phase1_media_map.json"
    existing_data = json.loads(media_map_path.read_text(encoding="utf-8")) if media_map_path.exists() else {"lookup": {}, "files": []}
    media_lookup = existing_data.get("lookup", {})
    unique_targets = {item["norm_path"]: item for item in existing_data.get("files", [])}

    new_targets = []
    missing_srcs = []
    for src in all_srcs:
        parsed = urllib.parse.urlparse(src)
        path = parsed.path
        if not path.startswith("/"):
            # Could be relative to root (2004 static) or /cms/
            cand_cms = "/cms/" + path.lstrip("/")
            cand_root = "/" + path.lstrip("/")
            norm_cms = urllib.parse.unquote(cand_cms).lower().replace("//", "/")
            norm_root = urllib.parse.unquote(cand_root).lower().replace("//", "/")
            norm_path = norm_cms if norm_cms in asset_map else norm_root
        else:
            norm_path = urllib.parse.unquote(path).lower().replace("//", "/")

        match = asset_map.get(norm_path)
        if not match:
            bname = Path(norm_path).name
            if bname in basename_map:
                ts, orig_url, mime, resolved_norm = basename_map[bname]
                match = (ts, orig_url, mime)
                norm_path = resolved_norm

        if not match:
            missing_srcs.append((src, norm_path))
            continue

        ts, orig_url, mime = match
        local_fname = clean_filename(norm_path)
        local_rel = f"/images/vessels/{local_fname}"
        media_lookup[src] = local_rel
        media_lookup[norm_path] = local_rel
        if norm_path not in unique_targets:
            item = {
                "norm_path": norm_path,
                "timestamp": ts,
                "original_url": orig_url,
                "wayback_raw_url": f"https://web.archive.org/web/{ts}id_/{urllib.parse.quote(orig_url, safe=':/?&=%')}",
                "local_file": str(IMG_OUT_DIR / local_fname),
                "local_url": local_rel,
            }
            unique_targets[norm_path] = item
            new_targets.append(item)

    media_map_path.write_text(json.dumps({"lookup": media_lookup, "files": list(unique_targets.values()), "missing": missing_srcs}, indent=2), encoding="utf-8")
    print(f"Found {len(new_targets)} new unique images for Phase 2 & 3 (Missing from CDX: {len(set(x[1] for x in missing_srcs))})")

    for idx, item in enumerate(new_targets, 1):
        out_f = Path(item["local_file"])
        if out_f.exists() and out_f.stat().st_size > 100:
            continue
        print(f"  [{idx:3d}/{len(new_targets)}] Downloading {out_f.name}...")
        try:
            raw = fetch_url(item["wayback_raw_url"], base_delay=2.5)
            out_f.write_bytes(raw)
        except Exception as e:
            print(f"    Failed to download {out_f.name}: {e}")
        time.sleep(2.0)

    print("\nPhase 2 & Phase 3 Download Complete!")


if __name__ == "__main__":
    main()
