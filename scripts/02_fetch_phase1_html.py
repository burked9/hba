#!/usr/bin/env python3
"""
Polite, resumable Wayback Machine downloader for Phase 1 (41 Grand Canal Boats)
and the full CDX asset index.
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE_DIR / "raw_archive" / "phase1_manifest.json"
CDX_ASSETS_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_assets.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HBA-Archival-Preservation/1.0"
}


def fetch_url(url: str, max_retries: int = 4, base_delay: float = 4.0) -> bytes:
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


def main():
    # 1. Fetch full CDX asset index (all statuscode=200 captures across the domain) if not present
    if not CDX_ASSETS_PATH.exists() or CDX_ASSETS_PATH.stat().st_size < 100:
        print("Fetching full CDX asset index for heritageboatassociation.ie...")
        cdx_url = (
            "https://web.archive.org/cdx/search/cdx?"
            "url=heritageboatassociation.ie/*&filter=statuscode:200&collapse=urlkey&output=json"
        )
        raw_cdx = fetch_url(cdx_url, base_delay=5.0)
        CDX_ASSETS_PATH.write_text(raw_cdx.decode("utf-8", errors="replace"), encoding="utf-8")
        print(f"Saved CDX asset index ({len(raw_cdx)} bytes) to {CDX_ASSETS_PATH}")
        time.sleep(3.5)

    # 2. Fetch all 41 Grand Canal Boat HTML articles
    vessels = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    total = len(vessels)
    downloaded = 0
    skipped = 0

    for idx, v in enumerate(vessels, 1):
        out_path = BASE_DIR / v["local_html_file"]
        if out_path.exists() and out_path.stat().st_size > 500:
            skipped += 1
            print(f"[{idx:2d}/{total}] {v['reg_number']:4s} already exists ({out_path.stat().st_size} B) - skipping")
            continue

        raw_url = v["wayback_raw_url"]
        print(f"[{idx:2d}/{total}] Fetching {v['reg_number']:4s} ({v['title']}) from {raw_url}...")
        try:
            content_bytes = fetch_url(raw_url)
        except Exception as e:
            print(f"  Primary URL failed ({e}), trying fallback print-view URL...")
            if v.get("fallback_pop_raw_url"):
                content_bytes = fetch_url(v["fallback_pop_raw_url"])
            else:
                raise

        text = content_bytes.decode("iso-8859-1", errors="replace")
        out_path.write_text(text, encoding="utf-8")
        downloaded += 1
        print(f"  -> Saved {len(content_bytes)} bytes to {out_path.name}")
        time.sleep(3.5)

    print(f"\nPhase 1 HTML scrape complete! Downloaded: {downloaded}, Skipped (already cached): {skipped}, Total: {total}")


if __name__ == "__main__":
    main()
