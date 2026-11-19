#!/usr/bin/env python3
"""
Parses all Phase 2 & Phase 3 Vessel Data into the HBA Pelican archive structure:
1. All 105 Joomla Vessels across all 11 Categories (`Itemid=64`)
2. All 28 Early Static HTML Vessel Pages (2004-2007 era: `vessels*.htm`, `LaganLightersEnquiry.htm`, `bolinderengines.htm`)
3. All WordPress Vessel & Essential Grid Pages (2020-2026 era)

Every version is preserved cleanly (both as its own historical record and cross-linked on the canonical vessel page).
Generates:
- `content/archive/vessels/<category_slug>/<vessel_slug>/index.md`
- `content/archive/vessels/<category_slug>/index.md`
- `content/archive/vessels/early-archive-2004-2007/<slug>/index.md`
- `content/archive/vessels/wordpress-2020-2026/<slug>/index.md`
- `content/archive/vessels/index.md`
- `content/data/vessels_registry.json`
- `theme/templates/vessels_table.html` (for the homepage Roll Call of Heritage Vessels)
"""
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE_DIR = Path(__file__).resolve().parent.parent
CMS_CAT_DIR = BASE_DIR / "raw_archive" / "cms_categories"
CMS_ART_DIR = BASE_DIR / "raw_archive" / "cms_articles"
STATIC_DIR = BASE_DIR / "raw_archive" / "static_2004_2007"
WP_DIR = BASE_DIR / "raw_archive" / "wp_2020_2026"
CDX_HTML_PATH = BASE_DIR / "raw_archive" / "cdx" / "cdx_html.json"
MEDIA_MAP_PATH = BASE_DIR / "data" / "phase1_media_map.json"

VESSELS_ARCHIVE_DIR = BASE_DIR / "content" / "archive" / "vessels"
DATA_DIR = BASE_DIR / "content" / "data"

CATEGORIES = [
    (32, "Grand Canal Boats", "grand-canal-boats", "Boats built for the Grand Canal Company in the 1920s and 1930s", "cat32.html"),
    (33, "Bye-Trader Boats", "bye-trader-boats", "Boats originally built as Bye-trader or Hack Boats", "cat_33.html"),
    (34, "Royal Canal Floats", "royal-canal-floats", "Barges known as Floats from the Royal Canal", "cat_34.html"),
    (35, "Steam Boats", "steam-boats", "Steam Barges, Tugs and Yachts from the 19th and 20th century", "cat_35.html"),
    (36, "Wooden Barges and Boats", "wooden-barges-and-boats", "Vessels with timber hulls", "cat_36.html"),
    (41, "Horse Boats", "horse-boats", "Horse drawn boats and lighters", "cat_41.html"),
    (37, "Dutch Motor and Sailing Barges", "dutch-barges", "Barges of the 19th and 20th centuries built in the Netherlands", "cat_37.html"),
    (38, "Other Vessels", "other-vessels", "Passenger Boats, Sand Barges, and other historic craft", "cat_38.html"),
    (39, "Modern Barges and Boats", "modern-barges-and-boats", "Modern vessels considered as exemplars of their style", "cat_39.html"),
    (40, "Boatyards, Boatbuilders and Engines", "boatyards-boatbuilders-and-engines", "Information on Boatyards, Boatbuilders and Engines", "cat_40.html"),
    (42, "Boat Photos", "boat-photos", "Historical Photo Collections of Boats and Barges", "cat_42.html"),
]


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


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
        "current draft": "draft",
        "weighed": "weighed",
        "engine": "engine",
        "engines": "engine",
        "former name": "former_names",
        "former names": "former_names",
        "name": "boat_name",
        "home base": "home_base",
    }
    return mapping.get(k, re.sub(r"[^a-z0-9]+", "_", k).strip("_"))


def resolve_local_img(src: str, media_lookup: dict) -> str:
    res = media_lookup.get(src)
    if not res:
        parsed = urllib.parse.urlparse(src)
        path = parsed.path
        if not path.startswith("/"):
            for prefix in ["/cms/", "/"]:
                norm = urllib.parse.unquote(prefix + path.lstrip("/")).lower().replace("//", "/")
                if norm in media_lookup:
                    res = media_lookup[norm]
                    break
        if not res:
            norm_path = urllib.parse.unquote(path).lower().replace("//", "/")
            res = media_lookup.get(norm_path, src)
    if res and res.endswith(".php"):
        return "/images/vessels/b-barge-line-up-2003.jpg"
    return res


def static_img(img_path: str) -> str:
    if not img_path:
        return "{static}/images/vessels/b-barge-line-up-2003.jpg"
    if img_path.startswith("{static}"):
        return img_path
    if img_path.startswith("/images/"):
        return "{static}" + img_path
    return img_path


def extract_joomla_article(soup: BeautifulSoup, media_lookup: dict, id_to_url: dict):
    main_div = soup.select_one("div.main-left-only") or soup
    content_tables = main_div.select("table.contentpaneopen")
    if len(content_tables) < 2:
        return {}, "", None, None, (None, None, [])

    body_table = content_tables[-1]
    create_td = body_table.select_one("td.createdate")
    created_date = create_td.get_text(strip=True) if create_td else None
    if create_td:
        create_td.decompose()

    mod_td = body_table.select_one("td.modifydate")
    modified_date = mod_td.get_text(strip=True) if mod_td else None
    if mod_td:
        mod_td.decompose()

    for toc in body_table.select("table.contenttoc, div.pagenavcounter, span.pagenav, div.pagenavbar"):
        toc.decompose()
    for p in body_table.find_all(["p", "div", "b", "strong"]):
        if p.get_text(strip=True).lower() == "technical details":
            p.decompose()

    specs = {}
    hero_img = None
    hero_caption = None

    for tbl in list(body_table.find_all("table")):
        txt = tbl.get_text()
        if "Technical Details" in txt or ("Built By" in txt and ("Length" in txt or "Year" in txt or "Construction" in txt)):
            first_img = tbl.find("img")
            if first_img and first_img.get("src"):
                hero_img = resolve_local_img(first_img["src"].strip(), media_lookup)
                parent_td = first_img.find_parent("td")
                if parent_td:
                    cap_txt = " ".join(parent_td.get_text().split())
                    hero_caption = cap_txt or first_img.get("alt") or first_img.get("title")
            for tr in tbl.find_all("tr"):
                tds = tr.find_all("td")
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

    gallery_images = []
    for img in body_table.find_all("img"):
        src = img.get("src", "").strip()
        if not src or any(x in src for x in ["pdf_button", "printButton", "emailButton", "arrow.png"]):
            img.decompose()
            continue
        local_src = resolve_local_img(src, media_lookup)
        img["src"] = static_img(local_src)
        alt = (img.get("title") or img.get("alt") or "").strip()
        if alt.lower().endswith((".jpg", ".gif", ".png")):
            alt = ""
        img["alt"] = alt
        gallery_images.append({"src": local_src, "caption": alt})

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

    for a in body_table.find_all("a"):
        href = a.get("href", "").replace("&amp;", "&")
        if "heritageboatassociation.ie/cms/index.php" in href and "task=view" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            aid = qs.get("id", [""])[0]
            if aid.isdigit() and int(aid) in id_to_url:
                a["href"] = "{filename}" + id_to_url[int(aid)].replace("/index.html", "/index.md")

    for tag in body_table.find_all(True):
        if tag.name in ("font", "span") or ":" in tag.name:
            tag.unwrap()

    content_td = body_table.find("td")
    inner_html = content_td.decode_contents() if content_td else str(body_table)
    markdown_body = md(inner_html, heading_style="ATX")
    markdown_body = markdown_body.replace("\xa0", " ")
    markdown_body = re.sub(r"\n{3,}", "\n\n", markdown_body).strip()

    return specs, markdown_body, created_date, modified_date, (hero_img, hero_caption, gallery_images)


def main():
    VESSELS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    media_data = json.loads(MEDIA_MAP_PATH.read_text(encoding="utf-8"))
    media_lookup = media_data.get("lookup", {})

    cdx_html = json.loads(CDX_HTML_PATH.read_text(encoding="utf-8"))[1:]
    wb_lookup = {}
    for row in cdx_html:
        ts, orig_url = row[1], row[2]
        if "/cms/" in orig_url and "task=view" in orig_url and "Itemid=64" in orig_url:
            u = orig_url.replace("&amp;", "&")
            if "index2.php" not in u and "limitstart=1" not in u:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                aid = qs.get("id", [""])[0].strip()
                if aid.isdigit():
                    aid_int = int(aid)
                    if aid_int not in wb_lookup or ts > wb_lookup[aid_int][0]:
                        wb_lookup[aid_int] = (ts, u)

    # First pass: collect all 105 articles across all 11 categories
    cat_entries = {}
    id_to_url = {}
    for cid, cat_name, cat_slug, cat_desc, cat_file in CATEGORIES:
        cpath = (BASE_DIR / "raw_archive" / cat_file) if cat_file == "cat32.html" else (CMS_CAT_DIR / cat_file)
        soup = BeautifulSoup(cpath.read_text(encoding="utf-8"), "html.parser")
        items = []
        for tr in soup.select("tr.sectiontableentry1, tr.sectiontableentry2"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            d_str = tds[0].get_text(strip=True)
            a = tds[1].find("a")
            if not a:
                continue
            title = " ".join(a.get_text().split())
            href = a.get("href", "").replace("&amp;", "&")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            aid = int(qs["id"][0])
            short_title = title.split(" - GCC")[0].split(" - Bye")[0].split(" - Royal")[0].split(" - Steam")[0].split(" - Horse")[0]
            v_slug = slugify(short_title) or f"vessel-{aid}"
            rel_url = f"/archive/vessels/{cat_slug}/{v_slug}/index.html"
            id_to_url[aid] = rel_url
            items.append({
                "article_id": aid,
                "title": title,
                "slug": v_slug,
                "listed_date": d_str,
                "category_id": cid,
                "category_name": cat_name,
                "category_slug": cat_slug,
                "url": rel_url,
            })
        cat_entries[cat_slug] = {
            "id": cid,
            "name": cat_name,
            "slug": cat_slug,
            "description": cat_desc,
            "items": items,
        }

    # Map early 2004-2007 static HTML vessel pages to their vessel registration/name
    static_vessel_files = sorted([
        p for p in STATIC_DIR.glob("*vessel*.htm*")
        if p.name not in ("vessels.htm", "vesselb.htm", "HBASiteSpring2007__vessels.htm")
    ] + [
        STATIC_DIR / "bolinderengines.htm",
        STATIC_DIR / "LaganLightersEnquiry.htm",
        STATIC_DIR / "shaneanderson.htm",
        STATIC_DIR / "waxerdunne.htm",
    ])

    early_Dir = VESSELS_ARCHIVE_DIR / "early-archive-2004-2007"
    early_Dir.mkdir(parents=True, exist_ok=True)
    early_by_reg = {}
    early_records = []

    for sf in static_vessel_files:
        if not sf.exists():
            continue
        raw_html = sf.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw_html, "html.parser")
        title_tag = soup.find("title")
        page_title = " ".join(title_tag.get_text().split()) if title_tag else sf.stem
        if page_title.lower() in ("vessels", "heritage boat association", "untitled document", ""):
            h_tag = soup.find(["h1", "h2", "h3", "b"])
            if h_tag:
                page_title = f"{sf.stem} - {' '.join(h_tag.get_text().split())[:60]}"
            else:
                page_title = sf.stem

        # Rewrite images in static page
        for img in soup.find_all("img"):
            src = img.get("src", "").strip()
            if not src or "menubutton" in src.lower():
                img.decompose()
                continue
            img["src"] = static_img(resolve_local_img(src, media_lookup))

        for tag in soup.find_all(True):
            if tag.name in ("font", "span", "script", "style") or ":" in tag.name:
                if tag.name in ("script", "style"):
                    tag.decompose()
                else:
                    tag.unwrap()

        body_el = soup.find("body") or soup
        md_text = md(str(body_el), heading_style="ATX").replace("\xa0", " ")
        md_text = re.sub(r"\n{3,}", "\n\n", md_text).strip()

        eslug = slugify(sf.stem.replace("HBASiteSpring2007__", "spring2007-"))
        e_dir = early_Dir / eslug
        e_dir.mkdir(parents=True, exist_ok=True)
        e_url = f"/archive/vessels/early-archive-2004-2007/{eslug}/index.html"

        e_md = f"""Title: {page_title} (2004–2007 Early Archive)
Date: 2006-01-01
Slug: archive/vessels/early-archive-2004-2007/{eslug}
Save_as: archive/vessels/early-archive-2004-2007/{eslug}/index.html
URL: archive/vessels/early-archive-2004-2007/{eslug}/index.html
Template: page

> **Archival Note:** This page was preserved from the early static HTML edition of `heritageboatassociation.ie` (2004–2007 era, original file: `{sf.name}`).

{md_text}
"""
        (e_dir / "index.md").write_text(e_md, encoding="utf-8")
        early_records.append({"title": page_title, "file": sf.name, "slug": eslug, "url": e_url})

        # Match to boat reg/name for cross-linking
        for key in ["34B", "35M", "39M", "41M", "45M", "47M", "49M", "50M", "52M", "61M", "68M", "71M", "72M", "95B", "4E", "Dabu", "Anchor", "Aqualegia", "Chang", "Misneach", "Knocknagow", "Float"]:
            if key.lower() in sf.name.lower():
                early_by_reg.setdefault(key.lower(), []).append({"title": page_title, "file": sf.name, "url": e_url})

    # Second pass: Parse all 105 Joomla Vessel pages and write Pelican pages
    all_registry = []
    for cat_slug, cinfo in cat_entries.items():
        cat_folder = VESSELS_ARCHIVE_DIR / cat_slug
        cat_folder.mkdir(parents=True, exist_ok=True)

        for item in cinfo["items"]:
            aid = item["article_id"]
            html_file = CMS_ART_DIR / f"item_64_id_{aid}.html"
            soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
            specs, md_body, c_date, m_date, img_info = extract_joomla_article(soup, media_lookup, id_to_url)
            hero_img, hero_caption, gallery = img_info

            # Append page 2 if multi-page article (id=94, 111, 181)
            p2_file = CMS_ART_DIR / f"item_64_id_{aid}_page2.html"
            if p2_file.exists():
                soup2 = BeautifulSoup(p2_file.read_text(encoding="utf-8"), "html.parser")
                _, md_body2, _, _, img_info2 = extract_joomla_article(soup2, media_lookup, id_to_url)
                md_body = f"{md_body}\n\n---\n\n{md_body2}"
                gallery.extend(img_info2[2])

            if not hero_img and gallery:
                hero_img = gallery[0]["src"]
                hero_caption = gallery[0]["caption"]

            reg_m = re.match(r"^([0-9]+[A-Z]+)", item["title"])
            reg_num = specs.get("reg_number") or (reg_m.group(1) if reg_m else item["title"].split(" - ")[0].strip())

            if not specs.get("year_built"):
                ym = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", item["title"])
                if ym:
                    specs["year_built"] = ym.group(1)

            if not specs.get("built_by"):
                for builder in ["Ringsend Dockyard Company", "Vickers (Ireland) Ltd.", "Vickers", "Ross & Walpole", "Liffey Dockyard", "Harland & Wolff", "W.J. Yarwood", "Boot"]:
                    if builder.lower() in md_body.lower():
                        specs["built_by"] = builder
                        break

            pub_date = parse_joomla_date(c_date or item["listed_date"])
            mod_date = parse_joomla_date(m_date) if m_date else pub_date
            ts, orig_u = wb_lookup.get(aid, ("20171031000000", f"http://heritageboatassociation.ie/cms/index.php?option=com_content&task=view&id={aid}&Itemid=64"))
            wb_public = f"https://web.archive.org/web/{ts}/{orig_u}"

            # Check for matching early 2004-2007 versions
            alt_versions = []
            for k, elist in early_by_reg.items():
                if k in item["title"].lower():
                    alt_versions.extend(elist)

            alt_md = ""
            if alt_versions:
                alt_lines = ["\n\n---\n\n### Earlier Archived Editions (2004–2007 Static Website)"]
                for av in alt_versions:
                    md_link = "{filename}" + av["url"].replace("/index.html", "/index.md")
                    alt_lines.append(f"- [{av['title']} (`{av['file']}`)]({md_link})")
                alt_md = "\n".join(alt_lines)

            entry = {
                "article_id": aid,
                "reg_number": reg_num,
                "title": item["title"],
                "slug": item["slug"],
                "category": cinfo["name"],
                "category_slug": cat_slug,
                "url": item["url"],
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
                "hero_image": hero_img or "/images/vessels/b-barge-line-up-2003.jpg",
                "hero_caption": hero_caption or item["title"],
                "original_url": orig_u,
                "wayback_url": wb_public,
                "alternate_editions": len(alt_versions),
            }
            all_registry.append(entry)
            item["entry"] = entry

            v_dir = cat_folder / item["slug"]
            v_dir.mkdir(parents=True, exist_ok=True)
            rel_save = f"archive/vessels/{cat_slug}/{item['slug']}/index.html"

            # Build Technical Details block at top of page
            spec_rows = []
            for label, key in [
                ("Registration / Name", "reg_number"),
                ("Category", "category"),
                ("Built By", "built_by"),
                ("Year Built", "year_built"),
                ("Construction", "construction"),
                ("Length", "length"),
                ("Beam", "beam"),
                ("Payload", "payload"),
                ("Draft", "draft"),
                ("Weighed", "weighed"),
                ("Engine", "engine"),
            ]:
                val = entry.get(key)
                if val:
                    spec_rows.append(f"| **{label}** | {val} |")

            specs_md_table = "\n".join(["| Specification | Detail |", "| :--- | :--- |"] + spec_rows)

            hero_block = ""
            if hero_img:
                hero_block = f"![{entry['hero_caption']}]({static_img(hero_img)})\n*{entry['hero_caption']}*\n\n"

            page_md = f"""Title: {item['title']}
Date: {pub_date}
Modified: {mod_date}
Slug: archive/vessels/{cat_slug}/{item['slug']}
Save_as: {rel_save}
URL: {rel_save}
Template: page
Category: {cinfo['name']}
Reg_Number: {reg_num}
Built_By: {entry['built_by']}
Year_Built: {entry['year_built']}
Hero_Image: {entry['hero_image']}
Wayback_URL: {wb_public}

[&larr; Back to {cinfo['name']}]({{filename}}/archive/vessels/{cat_slug}/index.md) | [&larr; Master Vessels Register]({{filename}}/archive/vessels/index.md)

{hero_block}### Technical Details

{specs_md_table}

---

### Vessel History

{md_body}{alt_md}

---
*Archival Provenance: Preserved from the Heritage Boat Association CMS (`Article ID {aid}`), last updated {mod_date}. [View Wayback Machine Snapshot &nearr;]({wb_public})*
"""
            (v_dir / "index.md").write_text(page_md, encoding="utf-8")

        # Write category index.md
        cards_html = ['<div class="vessel-grid">']
        for item in cinfo["items"]:
            ent = item["entry"]
            md_href = "{filename}" + ent["url"].replace("/index.html", "/index.md")
            cards_html.append(f"""
  <a href="{md_href}" class="vessel-card">
    <img src="{static_img(ent['hero_image'])}" class="vessel-thumb" alt="{ent['title']}" loading="lazy">
    <div class="vessel-info">
      <span class="vessel-reg" style="font-size: 1.15rem;">{ent['reg_number']}</span>
      <span class="vessel-title">{ent['title']}</span>
    </div>
  </a>""")
        cards_html.append("</div>")

        cat_index_md = f"""Title: {cinfo['name']} ({len(cinfo['items'])})
Date: 2017-10-31
Slug: archive/vessels/{cat_slug}
Save_as: archive/vessels/{cat_slug}/index.html
URL: archive/vessels/{cat_slug}/index.html
Template: page

[&larr; Back to All Vessel Categories]({{filename}}/archive/vessels/index.md)

{cinfo['description']}.

{"".join(cards_html)}
"""
        (cat_folder / "index.md").write_text(cat_index_md, encoding="utf-8")

    # Write early 2004-2007 index.md
    early_list_md = "\n".join([f"- **[{r['title']}]({{filename}}{r['url'].replace('/index.html', '/index.md')})** (`{r['file']}`)" for r in early_records])
    (early_Dir / "index.md").write_text(f"""Title: Early Website Vessel Pages (2004–2007 Static HTML Edition)
Date: 2007-11-18
Slug: archive/vessels/early-archive-2004-2007
Save_as: archive/vessels/early-archive-2004-2007/index.html
URL: archive/vessels/early-archive-2004-2007/index.html
Template: page

[&larr; Back to Master Vessels Register]({{filename}}/archive/vessels/index.md)

In accordance with our archival principle of preserving every historical edition of the HBA website, this section holds all **{len(early_records)}** static `.htm` vessel and book-draft pages captured between 2004 and Spring 2007 (prior to the Joomla CMS migration).

{early_list_md}
""", encoding="utf-8")

    # Parse WordPress 2020-2026 Vessel & Essential Grid pages
    wp_out_dir = VESSELS_ARCHIVE_DIR / "wordpress-2020-2026"
    wp_out_dir.mkdir(parents=True, exist_ok=True)
    wp_records = []
    for wf in sorted(WP_DIR.glob("*.html")):
        soup = BeautifulSoup(wf.read_text(encoding="utf-8", errors="replace"), "html.parser")
        title_tag = soup.find("title")
        wtitle = " ".join(title_tag.get_text().split()) if title_tag else wf.stem
        main_el = soup.select_one("div.theme-page, main, article, div.entry-content") or soup.find("body") or soup
        for tag in main_el.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        w_md = md(str(main_el), heading_style="ATX").replace("\xa0", " ")
        w_md = re.sub(r"\n{3,}", "\n\n", w_md).strip()
        wslug = slugify(wf.stem)
        w_sub = wp_out_dir / wslug
        w_sub.mkdir(parents=True, exist_ok=True)
        w_url = f"/archive/vessels/wordpress-2020-2026/{wslug}/index.html"
        (w_sub / "index.md").write_text(f"""Title: {wtitle} (2020–2026 WordPress Edition)
Date: 2026-05-12
Slug: archive/vessels/wordpress-2020-2026/{wslug}
Save_as: archive/vessels/wordpress-2020-2026/{wslug}/index.html
URL: archive/vessels/wordpress-2020-2026/{wslug}/index.html
Template: page

[&larr; Back to 2020–2026 WordPress Vessel Captures]({{filename}}/archive/vessels/wordpress-2020-2026/index.md)

> **Archival Note:** Preserved from the 2020–2026 WordPress edition of `heritageboatassociation.ie` (`{wf.stem.replace('__', '/')}`).

{w_md}
""", encoding="utf-8")
        wp_records.append({"title": wtitle, "slug": wslug, "url": w_url, "raw_name": wf.stem.replace("__", "/")})

    wp_list_md = "\n".join([f"- **[{r['title']}]({{filename}}{r['url'].replace('/index.html', '/index.md')})** (`/{r['raw_name']}/`)" for r in wp_records])
    (wp_out_dir / "index.md").write_text(f"""Title: WordPress Edition Vessel & Regional Overview Pages (2020–2026)
Date: 2026-05-12
Slug: archive/vessels/wordpress-2020-2026
Save_as: archive/vessels/wordpress-2020-2026/index.html
URL: archive/vessels/wordpress-2020-2026/index.html
Template: page

[&larr; Back to Master Vessels Register]({{filename}}/archive/vessels/index.md)

All **{len(wp_records)}** vessel overview pages and Essential Grid entries captured from the post-2020 WordPress edition of `heritageboatassociation.ie`.

{wp_list_md}
""", encoding="utf-8")

    # Save master JSON registry
    (DATA_DIR / "vessels_registry.json").write_text(json.dumps(all_registry, indent=2), encoding="utf-8")
    (BASE_DIR / "data" / "vessels_registry.json").write_text(json.dumps(all_registry, indent=2), encoding="utf-8")

    # Generate main /archive/vessels/index.md with category cards + full filterable table
    cat_cards = ['<div class="archive-grid">']
    for cid, cat_name, cat_slug, cat_desc, _ in CATEGORIES:
        items = cat_entries[cat_slug]["items"]
        thumb = items[0]["entry"]["hero_image"] if items else "/images/vessels/b-barge-line-up-2003.jpg"
        cat_cards.append(f"""
  <a href="{{filename}}/archive/vessels/{cat_slug}/index.md" class="archive-widget">
    <img src="{static_img(thumb)}" alt="{cat_name}" loading="lazy">
    <div class="archive-widget-content">
      <h3>{cat_name} ({len(items)})</h3>
      <p>{cat_desc}</p>
    </div>
  </a>""")
    # Add Early 2004-2007 and WordPress 2020-2026 cards
    cat_cards.append(f"""
  <a href="{{filename}}/archive/vessels/early-archive-2004-2007/index.md" class="archive-widget">
    <img src="{{static}}/images/vessels/b-barge-line-up-2003.jpg" alt="Early 2004-2007 Archive" loading="lazy">
    <div class="archive-widget-content">
      <h3>2004–2007 Static Edition ({len(early_records)})</h3>
      <p>Early vessel profiles &amp; Cool Metal – Clear Water draft pages from the original static site.</p>
    </div>
  </a>
  <a href="{{filename}}/archive/vessels/wordpress-2020-2026/index.md" class="archive-widget">
    <img src="{{static}}/images/vessels/b-72m.jpg" alt="WordPress 2020-2026 Edition" loading="lazy">
    <div class="archive-widget-content">
      <h3>2020–2026 WordPress Edition ({len(wp_records)})</h3>
      <p>Regional waterway vessel overviews &amp; Essential Grid entries from the later WordPress site.</p>
    </div>
  </a>
</div>""")

    (VESSELS_ARCHIVE_DIR / "index.md").write_text(f"""Title: Heritage Vessels Register & Archive
Date: 2017-10-31
Slug: archive/vessels
Save_as: archive/vessels/index.html
URL: archive/vessels/index.html
Template: page

The information on vessels was first gathered in 2006 for the book *Cool Metal – Clear Water* and expanded in *Fine Lines – Clear Water*. This archive preserves all **105 canonical entries** across 11 categories from the Joomla register, plus **{len(early_records)} early static HTML pages (2004–2007)** and **{len(wp_records)} WordPress overview pages (2020–2026)**.

{"".join(cat_cards)}
""", encoding="utf-8")

    # Generate theme/templates/vessels_table.html (vintage roll-call table for homepage)
    table_rows = []
    for v in all_registry:
        table_rows.append(f"""            <tr>
                <td><strong><a href="{{{{ SITEURL }}}}{v['url']}">{v['reg_number']}</a></strong></td>
                <td><a href="{{{{ SITEURL }}}}{v['url']}">{v['title']}</a></td>
                <td>{v['category']}</td>
                <td>{v['year_built'] or '—'}</td>
                <td>{v['built_by'] or '—'}</td>
            </tr>""")

    vessels_table_html = f"""<table class="vintage-table" style="width:100%">
        <thead>
            <tr>
                <th style="text-align: left;">Vessel</th>
                <th style="text-align: left;">Full Title</th>
                <th style="text-align: left;">Category</th>
                <th style="text-align: left;">Year</th>
                <th style="text-align: left;">Builder</th>
            </tr>
        </thead>
        <tbody>
{chr(10).join(table_rows)}
        </tbody>
    </table>
"""
    (BASE_DIR / "theme" / "templates" / "vessels_table.html").write_text(vessels_table_html, encoding="utf-8")

    print(f"Successfully generated:")
    print(f"  - {len(all_registry)} canonical Joomla Vessel & Boatyard pages across 11 categories")
    print(f"  - {len(early_records)} early 2004-2007 static HTML vessel pages")
    print(f"  - {len(wp_records)} WordPress 2020-2026 vessel/grid pages")
    print(f"  - theme/templates/vessels_table.html & content/data/vessels_registry.json")


if __name__ == "__main__":
    main()
