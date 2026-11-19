#!/usr/bin/env python3
"""
Downloads all 128+ unique images for Phase 1 (41 Grand Canal Boats), plus 68M Page 2
and its images, normalizing filenames for Pelican / GitHub Pages.
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
MANIFEST_PATH = BASE_DIR / "raw_archive" / "phase1_manifest.json"
CDX_ASSETS_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_assets.json"
IMG_OUT_DIR = BASE_DIR / "content" / "images" / "vessels"
MEDIA_MAP_PATH = BASE_DIR / "data" / "phase1_media_map.json"

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
    # norm_path is e.g. /cms/images/stories/41m raised by gcc/w a10 41m.jpg
    rel = norm_path
    for prefix in ["/cms/images/stories/", "/cms/images/", "/images/"]:
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
        if not src or any(x in src for x in ["pdf_button", "printButton", "emailButton", "arrow.png", "logo.png"]):
            continue
        srcs.append(src)
    return srcs


def main():
    IMG_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch 68M Page 2 (id=94, limitstart=1) if not cached
    p2_path = BASE_DIR / "raw_archive" / "cms_articles" / "item_64_id_94_page2.html"
    if not p2_path.exists() or p2_path.stat().st_size < 500:
        p2_url = "https://web.archive.org/web/20171031090203id_/http://heritageboatassociation.ie/cms/index.php?option=com_content&task=view&id=94&Itemid=64&limit=1&limitstart=1"
        print(f"Fetching 68M Page 2 from {p2_url}...")
        raw_p2 = fetch_url(p2_url)
        p2_path.write_text(raw_p2.decode("iso-8859-1", errors="replace"), encoding="utf-8")
        print(f"  -> Saved {len(raw_p2)} bytes to {p2_path.name}")
        time.sleep(2.5)

    # 2. Build CDX asset lookup
    cdx_assets = json.loads(CDX_ASSETS_PATH.read_text(encoding="utf-8"))[1:]
    asset_map = {}
    for row in cdx_assets:
        ts, orig_url, mime, status = row[1], row[2], row[3], row[4]
        parsed = urllib.parse.urlparse(orig_url)
        norm_path = urllib.parse.unquote(parsed.path).lower().replace("//", "/")
        if norm_path not in asset_map or ts > asset_map[norm_path][0]:
            asset_map[norm_path] = (ts, orig_url, mime)

    # 3. Collect all image URLs across all 41 boats (+ 68M page 2 + category header B 72M.jpg + B Barge Line Up 2003.jpg)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    all_srcs = [
        "http://heritageboatassociation.ie/cms/images/stories/B Barge Line Up 2003.jpg",
        "http://heritageboatassociation.ie/cms/images/stories/B 72M.jpg",
    ]
    for v in manifest:
        html_text = (BASE_DIR / v["local_html_file"]).read_text(encoding="utf-8")
        all_srcs.extend(extract_imgs_from_html(html_text))
    if p2_path.exists():
        all_srcs.extend(extract_imgs_from_html(p2_path.read_text(encoding="utf-8")))

    # Deduplicate by norm_path
    media_map = {}
    unique_targets = {}
    for src in all_srcs:
        parsed = urllib.parse.urlparse(src)
        path = parsed.path
        if not path.startswith("/"):
            path = "/cms/" + path.lstrip("/")
        norm_path = urllib.parse.unquote(path).lower().replace("//", "/")
        if norm_path not in asset_map:
            print(f"WARNING: Image not in CDX: {src} ({norm_path})")
            continue
        ts, orig_url, mime = asset_map[norm_path]
        local_fname = clean_filename(norm_path)
        local_rel = f"/images/vessels/{local_fname}"
        media_map[src] = local_rel
        media_map[norm_path] = local_rel
        unique_targets[norm_path] = {
            "norm_path": norm_path,
            "timestamp": ts,
            "original_url": orig_url,
            "wayback_raw_url": f"https://web.archive.org/web/{ts}id_/{ urllib.parse.quote(orig_url, safe=':/?&=%') }",
            "local_file": str(IMG_OUT_DIR / local_fname),
            "local_url": local_rel,
        }

    MEDIA_MAP_PATH.write_text(json.dumps({"lookup": media_map, "files": list(unique_targets.values())}, indent=2), encoding="utf-8")
    targets = list(unique_targets.values())
    total = len(targets)
    print(f"Found {total} unique images to download for Phase 1.")

    downloaded = 0
    skipped = 0
    for idx, item in enumerate(targets, 1):
        out_file = Path(item["local_file"])
        if out_file.exists() and out_file.stat().st_size > 100:
            skipped += 1
            continue
        wb_url = item["wayback_raw_url"]
        print(f"[{idx:3d}/{total}] Downloading {out_file.name} from {wb_url}...")
        data = fetch_url(wb_url, base_delay=2.5)
        out_file.write_bytes(data)
        downloaded += 1
        time.sleep(2.0)

    print(f"\nPhase 1 Media Download Complete! Downloaded: {downloaded}, Skipped: {skipped}, Total: {total}")


if __name__ == "__main__":
    main()
