#!/usr/bin/env python3
"""
Phase 4 Downloader & Parser:
Archives the entire remaining Heritage Boat Association website across all eras:
1. Joomla Category Index Pages for Latest News (Itemid=35), Photos (Itemid=43), Memories (Itemid=74),
   Publications & References (Itemid=42), Resources (Itemid=78), About Us (Itemid=57), What's On (com_eventlist), Links (com_weblinks)
2. All 440+ remaining Joomla articles (`task=view` across all Itemids, including multi-page continuations)
3. All 18 standalone archived PDF and Word documents (`/cms/documents/...`, `GCC_Court_of_Inquiry_May_1935-OCR.pdf`, etc.)
4. All 196 remaining WordPress pages (2020-2026 era)
5. All remaining images referenced across these articles
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

CMS_CAT_DIR = BASE_DIR / "raw_archive" / "cms_categories"
CMS_ART_DIR = BASE_DIR / "raw_archive" / "cms_articles"
WP_DIR = BASE_DIR / "raw_archive" / "wp_2020_2026"
DOCS_OUT_DIR = BASE_DIR / "content" / "documents"
IMG_OUT_DIR = BASE_DIR / "content" / "images" / "archive"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HBA-Archival-Preservation/1.0"
}


def fetch_url(url: str, max_retries: int = 4, base_delay: float = 2.5) -> bytes:
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
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
    for prefix in ["/cms/images/stories/", "/cms/images/", "/images/", "/cms/documents/"]:
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
    for d in [CMS_CAT_DIR, CMS_ART_DIR, WP_DIR, DOCS_OUT_DIR, IMG_OUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    cdx_html = json.loads(CDX_HTML_PATH.read_text(encoding="utf-8"))[1:]
    cdx_assets = json.loads(CDX_ASSETS_PATH.read_text(encoding="utf-8"))[1:]

    # 1. Download Phase 4 Joomla Category Index Pages
    p4_cats = [
        ("cat_news_0.html", "20171030193408", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=1&id=19&Itemid=35&limit=50&limitstart=0"),
        ("cat_news_50.html", "20171029085602", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=1&id=19&Itemid=35&limit=50&limitstart=50"),
        ("cat_news_100.html", "20171029085607", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=1&id=19&Itemid=35&limit=50&limitstart=100"),
        ("cat_news_150.html", "20171029085612", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=1&id=19&Itemid=35&limit=50&limitstart=150"),
        ("cat_photos_0.html", "20171031210836", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=11&id=21&Itemid=43&limit=50&limitstart=0"),
        ("cat_photos_50.html", "20171030104937", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=11&id=21&Itemid=43&limit=50&limitstart=50"),
        ("cat_memories.html", "20171024172228", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=15&id=44&Itemid=74&limit="),
        ("cat_publications.html", "20171024235945", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=6&id=13&Itemid=42&limit="),
        ("cat_resources.html", "20171024235953", "http://heritageboatassociation.ie/cms/index.php?option=com_content&task=category&sectionid=3&id=45&Itemid=78&limit="),
        ("cms_frontpage.html", "20171220170351", "http://heritageboatassociation.ie/cms/index.php?option=com_frontpage&Itemid=1"),
        ("cms_weblinks_2.html", "20171220170348", "http://heritageboatassociation.ie/cms/index.php?option=com_weblinks&catid=2&Itemid=37"),
        ("cms_weblinks_20.html", "20171030150729", "http://heritageboatassociation.ie/cms/index.php?option=com_weblinks&catid=20&Itemid=37"),
        ("cms_weblinks_22.html", "20171030150722", "http://heritageboatassociation.ie/cms/index.php?option=com_weblinks&catid=22&Itemid=37"),
        ("cms_events.html", "20171220170346", "http://heritageboatassociation.ie/cms/index.php?option=com_eventlist&Itemid=61"),
    ]
    print("=== Step 1: Downloading Phase 4 Joomla Category Index Pages ===")
    for fname, ts, u in p4_cats:
        out_f = CMS_CAT_DIR / fname
        if out_f.exists() and out_f.stat().st_size > 500:
            continue
        print(f"  Fetching {fname}...")
        raw = fetch_url(f"https://web.archive.org/web/{ts}id_/{u}")
        out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        time.sleep(2.0)

    # 2. Download all remaining Joomla articles across all Itemids
    print("\n=== Step 2: Downloading All Remaining Joomla Articles ===")
    existing_ids = {int(p.stem.split("_id_")[1].split("_")[0]) for p in CMS_ART_DIR.glob("item_*_id_*.html")}
    main_articles = {}
    pop_articles = {}
    extra_pages = []

    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        if "/cms/" in orig_url and "task=view" in orig_url:
            u = orig_url.replace("&amp;", "&")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            aid = qs.get("id", [""])[0].strip()
            itemid = qs.get("Itemid", ["none"])[0].strip().split("heritage")[0]
            if not aid.isdigit():
                continue
            aid_int = int(aid)
            if "index2.php" in u or "pop=1" in u:
                pop_articles[aid_int] = (itemid, ts, u)
            elif "limitstart=" in u and "limitstart=0" not in u:
                lstart = qs.get("limitstart", ["1"])[0].strip()
                extra_pages.append((itemid, aid_int, lstart, ts, u))
            else:
                if aid_int not in main_articles or ts > main_articles[aid_int][1]:
                    main_articles[aid_int] = (itemid, ts, u)

    # Include any articles that only have a pop=1 snapshot
    for aid_int, (itemid, ts, u) in pop_articles.items():
        if aid_int not in main_articles:
            main_articles[aid_int] = (itemid, ts, u)

    to_fetch = [(aid, info) for aid, info in sorted(main_articles.items()) if aid not in existing_ids]
    print(f"Found {len(to_fetch)} new Joomla articles to download (plus {len(extra_pages)} multi-page continuations).")

    for idx, (aid, (itemid, ts, u)) in enumerate(to_fetch, 1):
        out_f = CMS_ART_DIR / f"item_{itemid}_id_{aid}.html"
        if out_f.exists() and out_f.stat().st_size > 500:
            continue
        wb_u = f"https://web.archive.org/web/{ts}id_/{u}"
        print(f"  [{idx:3d}/{len(to_fetch)}] Fetching item_{itemid}_id_{aid}.html...")
        try:
            raw = fetch_url(wb_u)
        except Exception as e:
            if aid in pop_articles:
                _, pts, pu = pop_articles[aid]
                raw = fetch_url(f"https://web.archive.org/web/{pts}id_/{pu}")
            else:
                print(f"    Failed id={aid}: {e}")
                continue
        out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        time.sleep(2.0)

    for itemid, aid, lstart, ts, u in extra_pages:
        out_f = CMS_ART_DIR / f"item_{itemid}_id_{aid}_limitstart{lstart}.html"
        if out_f.exists() and out_f.stat().st_size > 500:
            continue
        print(f"  Fetching continuation item_{itemid}_id_{aid}_limitstart{lstart}.html...")
        try:
            raw = fetch_url(f"https://web.archive.org/web/{ts}id_/{u}")
            out_f.write_text(raw.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        except Exception as e:
            print(f"    Failed continuation id={aid}: {e}")
        time.sleep(2.0)

    # 3. Download all 18 standalone PDF and Word documents
    print("\n=== Step 3: Downloading All 18 Standalone PDF & Word Documents ===")
    real_docs = []
    for row in cdx_assets:
        ts, orig_url, mime = row[1], row[2], row[3]
        if "do_pdf=1" in orig_url:
            continue
        if orig_url.lower().endswith((".pdf", ".doc", ".docx")) or "pdf" in mime.lower() or "msword" in mime.lower():
            real_docs.append((ts, orig_url, mime))

    for idx, (ts, orig_url, mime) in enumerate(real_docs, 1):
        parsed = urllib.parse.urlparse(orig_url)
        bname = Path(urllib.parse.unquote(parsed.path)).name
        clean_bname = re.sub(r"[^a-zA-Z0-9._-]+", "_", bname)
        out_f = DOCS_OUT_DIR / clean_bname
        if out_f.exists() and out_f.stat().st_size > 500:
            print(f"  [{idx:2d}/{len(real_docs)}] {clean_bname} already exists")
            continue
        wb_u = f"https://web.archive.org/web/{ts}id_/{urllib.parse.quote(orig_url, safe=':/?&=%')}"
        print(f"  [{idx:2d}/{len(real_docs)}] Downloading document {clean_bname} ({ts})...")
        try:
            raw = fetch_url(wb_u, base_delay=3.0)
            out_f.write_bytes(raw)
        except Exception as e:
            print(f"    Failed doc {clean_bname}: {e}")
        time.sleep(2.5)

    # 4. Download remaining WordPress 2020-2026 articles/pages (skipping medicenter theme dummy pages)
    print("\n=== Step 4: Downloading Remaining WordPress 2020-2026 Content Pages ===")
    skip_wp_prefixes = ("medicenter_", "doctors/", "departments/", "gallery-", "home-style", "contact-style", "medical-care", "sample-page", "search-template", "shortcodes", "my-account", "shop")
    wp_to_fetch = []
    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        path = urllib.parse.urlparse(orig_url).path
        if "/cms/" not in path and not path.endswith((".htm", ".html")) and not path.endswith("/HBASiteSpring2007/"):
            clean_p = path.strip("/")
            if any(clean_p.startswith(pfx) for pfx in skip_wp_prefixes):
                continue
            slug = clean_p.replace("/", "__") or "wp_root"
            out_f = WP_DIR / f"{slug}.html"
            if not out_f.exists() or out_f.stat().st_size < 500:
                wp_to_fetch.append((slug, ts, orig_url, out_f))

    print(f"Found {len(wp_to_fetch)} remaining WordPress content pages to download.")
    for idx, (slug, ts, orig_url, out_f) in enumerate(wp_to_fetch, 1):
        print(f"  [{idx:3d}/{len(wp_to_fetch)}] Fetching WP {slug}...")
        try:
            raw = fetch_url(f"https://web.archive.org/web/{ts}id_/{orig_url}")
            out_f.write_text(raw.decode("utf-8", errors="replace"), encoding="utf-8")
        except Exception as e:
            print(f"    Failed WP {slug}: {e}")
        time.sleep(2.0)

    print("\nPhase 4 HTML & Document Download Complete!")


if __name__ == "__main__":
    main()
