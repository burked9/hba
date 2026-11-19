#!/usr/bin/env python3
"""
Parses all 41 Phase 1 Grand Canal Boat HTML files into:
1. Clean Pelican Markdown files (`content/vessels/grand-canal-boats/<slug>.md`)
2. Master JSON registry (`data/vessels_registry.json`)
3. Phase 1 QA & Anomaly report (`data/phase1_qa_report.md`)
"""
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE_DIR / "raw_archive" / "phase1_manifest.json"
MEDIA_MAP_PATH = BASE_DIR / "data" / "phase1_media_map.json"
REGISTRY_PATH = BASE_DIR / "data" / "vessels_registry.json"
MD_OUT_DIR = BASE_DIR / "content" / "vessels" / "grand-canal-boats"
QA_REPORT_PATH = BASE_DIR / "data" / "phase1_qa_report.md"


def parse_joomla_date(date_str: str) -> str:
    if not date_str:
        return "2008-09-01"
    cleaned = re.sub(r"Last Updated\s*\(\s*|\s*\)", "", date_str).strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "2008-09-01"


def normalize_spec_key(raw_key: str) -> str:
    k = raw_key.lower().replace(":", "").strip()
    mapping = {
        "reg number": "reg_number",
        "registration number": "reg_number",
        "reg no": "reg_number",
        "built by": "built_by",
        "builder": "built_by",
        "year": "year_built",
        "built": "year_built",
        "construction": "construction",
        "hull": "construction",
        "length": "length",
        "beam": "beam",
        "payload": "payload",
        "cargo capacity": "payload",
        "draft": "draft",
        "draught": "draft",
        "weighed": "weighed",
        "engine": "engine",
        "engines": "engine",
        "former name": "former_names",
        "former names": "former_names",
        "name": "boat_name",
    }
    return mapping.get(k, re.sub(r"[^a-z0-9]+", "_", k).strip("_"))


def resolve_local_img(src: str, media_lookup: dict) -> str:
    if src in media_lookup:
        return media_lookup[src]
    parsed = urllib.parse.urlparse(src)
    path = parsed.path
    if not path.startswith("/"):
        path = "/cms/" + path.lstrip("/")
    norm_path = urllib.parse.unquote(path).lower().replace("//", "/")
    return media_lookup.get(norm_path, src)


def extract_article_body(soup: BeautifulSoup, media_lookup: dict, id_to_slug: dict):
    main_div = soup.select_one("div.main-left-only") or soup
    content_tables = main_div.select("table.contentpaneopen")
    if len(content_tables) < 2:
        return {}, "", None, None, []

    body_table = content_tables[1]
    create_td = body_table.select_one("td.createdate")
    created_date = create_td.get_text(strip=True) if create_td else None
    if create_td:
        create_td.decompose()

    mod_td = body_table.select_one("td.modifydate")
    modified_date = mod_td.get_text(strip=True) if mod_td else None
    if mod_td:
        mod_td.decompose()

    # Remove Joomla pagination/TOC tables inside body
    for toc in body_table.select("table.contenttoc, div.pagenavcounter, span.pagenav, div.pagenavbar"):
        toc.decompose()
    for p in body_table.find_all(["p", "div", "b", "strong"]):
        if p.get_text(strip=True).lower() == "technical details":
            p.decompose()

    specs = {}
    hero_img = None
    hero_caption = None

    # Find Technical Details table (either has caption 'Technical Details' or contains 'Reg Number:' / 'Built By:')
    for tbl in body_table.find_all("table"):
        txt = tbl.get_text()
        if "Technical Details" in txt or ("Built By" in txt and "Length" in txt):
            # Extract hero image if inside the spec table
            first_img = tbl.find("img")
            if first_img and first_img.get("src"):
                hero_img = resolve_local_img(first_img["src"].strip(), media_lookup)
                parent_td = first_img.find_parent("td")
                if parent_td:
                    cap_txt = " ".join(parent_td.get_text().split())
                    hero_caption = cap_txt or first_img.get("alt") or first_img.get("title")
            for tr in tbl.find_all("tr"):
                tds = tr.find_all("td")
                # Remove any td that holds the rowspan image
                data_tds = [td for td in tds if not td.find("img")]
                if len(data_tds) >= 2:
                    raw_k = " ".join(data_tds[0].get_text().split())
                    raw_v = " / ".join(
                        [" ".join(p.get_text().split()) for p in data_tds[1].find_all("p")]
                    ) or " ".join(data_tds[1].get_text().split())
                    if raw_k and raw_v:
                        specs[normalize_spec_key(raw_k)] = raw_v
            tbl.decompose()
            break

    # Rewrite remaining images and links in body_table
    gallery_images = []
    for img in body_table.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue
        local_src = resolve_local_img(src, media_lookup)
        img["src"] = local_src
        alt = (img.get("title") or img.get("alt") or "").strip()
        # Clean default filename alts
        if alt.lower().endswith((".jpg", ".gif", ".png")):
            alt = ""
        img["alt"] = alt
        gallery_images.append({"src": local_src, "caption": alt})

    # Convert layout tables containing only images into clean Markdown images
    for tbl in list(body_table.find_all("table")):
        imgs = tbl.find_all("img")
        if imgs:
            container = soup.new_tag("div")
            for im in imgs:
                cap = (im.get("alt") or im.get("title") or "").strip()
                p_tag = soup.new_tag("p")
                im_copy = soup.new_tag("img", src=im["src"], alt=cap, title=cap)
                p_tag.append(im_copy)
                if cap:
                    br = soup.new_tag("br")
                    p_tag.append(br)
                    em = soup.new_tag("em")
                    em.string = cap
                    p_tag.append(em)
                container.append(p_tag)
            tbl.replace_with(container)

    # Rewrite internal Joomla links to local Pelican vessel slugs where possible
    for a in body_table.find_all("a"):
        href = a.get("href", "").replace("&amp;", "&")
        if "heritageboatassociation.ie/cms/index.php" in href and "task=view" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            aid = qs.get("id", [""])[0]
            if aid.isdigit() and int(aid) in id_to_slug:
                a["href"] = f"/vessels/grand-canal-boats/{id_to_slug[int(aid)]}/"

    # Unwrap noisy inline font/span and MS Word smart tags (st1:*, o:*, w:*)
    for tag in body_table.find_all(True):
        if tag.name in ("font", "span") or ":" in tag.name:
            tag.unwrap()

    # Unwrap outer table.contentpaneopen cells so markdownify doesn't wrap the whole article in a pipe table!
    content_td = body_table.find("td")
    inner_html = content_td.decode_contents() if content_td else str(body_table)

    markdown_body = md(inner_html, heading_style="ATX")
    # Clean up excessive blank lines and non-breaking spaces
    markdown_body = markdown_body.replace("\xa0", " ")
    markdown_body = re.sub(r"\n{3,}", "\n\n", markdown_body).strip()

    return specs, markdown_body, created_date, modified_date, (hero_img, hero_caption, gallery_images)


def yaml_escape(val: str) -> str:
    if val is None:
        return '""'
    s = str(val).replace('"', '\\"')
    return f'"{s}"'


def main():
    MD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    media_data = json.loads(MEDIA_MAP_PATH.read_text(encoding="utf-8")) if MEDIA_MAP_PATH.exists() else {"lookup": {}}
    media_lookup = media_data.get("lookup", {})

    id_to_slug = {v["article_id"]: v["slug"] for v in manifest}
    registry = []
    anomalies = []

    for v in manifest:
        html_path = BASE_DIR / v["local_html_file"]
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        specs, md_body, c_date, m_date, img_info = extract_article_body(soup, media_lookup, id_to_slug)
        hero_img, hero_caption, gallery = img_info

        # Check if 68M has page 2
        if v["article_id"] == 94:
            p2_path = BASE_DIR / "raw_archive" / "cms_articles" / "item_64_id_94_page2.html"
            if p2_path.exists():
                soup2 = BeautifulSoup(p2_path.read_text(encoding="utf-8"), "html.parser")
                _, md_body2, _, _, img_info2 = extract_article_body(soup2, media_lookup, id_to_slug)
                # Strip duplicate link to title at top of page 2
                md_body2 = re.sub(r"^\[68M[^\]]*\]\([^\)]*\)\s*", "", md_body2).strip()
                md_body = f"{md_body}\n\n---\n\n{md_body2}"
                gallery.extend(img_info2[2])

        if not hero_img and gallery:
            hero_img = gallery[0]["src"]
            hero_caption = gallery[0]["caption"]

        pub_date = parse_joomla_date(c_date or v["listed_date"])
        mod_date = parse_joomla_date(m_date) if m_date else pub_date

        # Extract year from title if not in specs
        if not specs.get("year_built"):
            ym = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", v["title"])
            if ym:
                specs["year_built"] = ym.group(1)

        # Extract builder from prose if not in specs
        if not specs.get("built_by"):
            for builder in ["Ringsend Dockyard Company", "Vickers (Ireland) Ltd.", "Vickers", "Ross & Walpole", "Liffey Dockyard"]:
                if builder.lower() in md_body.lower():
                    specs["built_by"] = builder
                    break

        # Track anomalies for QA report
        if not specs:
            anomalies.append(f"- **{v['reg_number']} ({v['title']})**: No standard Technical Details table found.")
        if not hero_img:
            anomalies.append(f"- **{v['reg_number']} ({v['title']})**: No images found on page.")

        entry = {
            "article_id": v["article_id"],
            "reg_number": specs.get("reg_number", v["reg_number"]),
            "title": v["title"],
            "slug": v["slug"],
            "category": "Grand Canal Boats",
            "url": f"/vessels/grand-canal-boats/{v['slug']}/",
            "date": pub_date,
            "modified": mod_date,
            "built_by": specs.get("built_by", ""),
            "year_built": specs.get("year_built", ""),
            "construction": specs.get("construction", ""),
            "length": specs.get("length", ""),
            "beam": specs.get("beam", ""),
            "payload": specs.get("payload", ""),
            "draft": specs.get("draft", ""),
            "weighed": specs.get("weighed", ""),
            "engine": specs.get("engine", ""),
            "hero_image": hero_img or "",
            "hero_caption": hero_caption or "",
            "image_count": (1 if hero_img else 0) + len(gallery),
            "original_url": v["original_url"],
            "wayback_url": v["wayback_public_url"],
        }
        registry.append(entry)

        # Write Pelican Markdown file
        frontmatter = [
            "---",
            f"Title: {yaml_escape(v['title'])}",
            f"Slug: {v['slug']}",
            "Category: Grand Canal Boats",
            "Subcategory: Grand Canal Boats",
            f"Date: {pub_date}",
            f"Modified: {mod_date}",
            f"Reg_Number: {yaml_escape(entry['reg_number'])}",
            f"Built_By: {yaml_escape(entry['built_by'])}",
            f"Year_Built: {yaml_escape(entry['year_built'])}",
            f"Construction: {yaml_escape(entry['construction'])}",
            f"Length: {yaml_escape(entry['length'])}",
            f"Beam: {yaml_escape(entry['beam'])}",
            f"Payload: {yaml_escape(entry['payload'])}",
            f"Draft: {yaml_escape(entry['draft'])}",
            f"Weighed: {yaml_escape(entry['weighed'])}",
            f"Engine: {yaml_escape(entry['engine'])}",
            f"Hero_Image: {yaml_escape(entry['hero_image'])}",
            f"Hero_Caption: {yaml_escape(entry['hero_caption'])}",
            f"Original_URL: {yaml_escape(v['original_url'])}",
            f"Wayback_URL: {yaml_escape(v['wayback_public_url'])}",
            f"Article_ID: {v['article_id']}",
            "---",
            "",
            md_body,
            "",
        ]
        md_file = MD_OUT_DIR / f"{v['slug']}.md"
        md_file.write_text("\n".join(frontmatter), encoding="utf-8")

    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    qa_lines = [
        "# Phase 1 QA Report: 41 Grand Canal Boats",
        "",
        f"- **Total Boats Processed:** {len(registry)}",
        f"- **Total Markdown Files Generated:** {len(list(MD_OUT_DIR.glob('*.md')))}",
        f"- **Total Unique Images Referenced:** {len(media_data.get('files', []))}",
        "",
        "## Anomalies / Notes",
    ]
    if anomalies:
        qa_lines.extend(anomalies)
    else:
        qa_lines.append("- None! All 41 boats parsed cleanly with technical specifications and images.")

    QA_REPORT_PATH.write_text("\n".join(qa_lines), encoding="utf-8")
    print(f"Generated {len(registry)} Pelican Markdown files in {MD_OUT_DIR}")
    print(f"Saved master registry to {REGISTRY_PATH}")
    print("\n".join(qa_lines))


if __name__ == "__main__":
    main()
