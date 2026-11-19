Title: Admin Portal & Archival Status
Date: 2026-11-19
Slug: admin
Template: page

# HBA Archival Roadmap & Status

## [x] Phase 1: Complete 41 Grand Canal Boats
- Downloaded all 41 Grand Canal M-Boat articles + Page 2 of `68M`.
- Downloaded all 143 unique photographs from the Wayback Machine.
- Extracted Technical Details tables and narratives into Pelican Markdown and `vessels_registry.json`.

## [x] Phase 2: All Other Vessels (52 Vessels across 8 Categories)
- Downloaded Bye-Trader Boats (9), Royal Canal Floats (4), Steam Boats (10), Wooden Barges & Boats (6), Horse Boats (10), Dutch Barges (3), Other Vessels (9), and Modern Barges (1).
- Downloaded all 536 remaining vessel & static era images (679 images total).

## [x] Phase 3: Boatyards, Photos & Alternate Era Editions
- Archived Boatyards, Boatbuilders & Engines (7) and Boat Photos (5).
- Archived all 77 static HTML pages from the 2004–2007 era (`raw_archive/static_2004_2007/`) and converted 32 early vessel pages with cross-links to the canonical vessel profiles.
- Archived all 42 WordPress vessel & regional overview pages from the 2020–2026 era.

## [ ] Phase 4: Remaining Website Sections & Documents (Ready to Resume)
- Run `python3 scripts/07_fetch_phase4_all.py` to download remaining Memories, Publications, Resources, Photo Galleries, Latest News, and 18 standalone PDF/Word documents.
