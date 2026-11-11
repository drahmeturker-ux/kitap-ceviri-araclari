# kitap-ceviri-araclari

Helper scripts for the `translate-book` skill (two-column medical textbooks, PDF → Turkish, original layout).

| Script | What it does |
|---|---|
| `extract.py book.pdf FIRST LAST out_dir` | Reads a PDF page range with pdfplumber; writes `layout.json` (items in reading order with per-page/per-column letter shares, column frames, captions, running heads, chapter title, author line) and `source.md` (`<<id>> text` blocks to translate). |
| `checks.py layout.json tr.json [glossary.json]` | Compares source and translation per item: numbers (decimal comma allowed), abbreviations kept / none invented, parenthetical citations unchanged, bold `Fig.` markers, glossary targets used; lists `[kaynakta: …]` notes. Exit code 1 on problems. |
| `layout.py book.pdf layout.json tr.json out.pdf` | Removes the source text from the page content streams and draws the translation into the original column frames (largest font scale that fits each page), captions in their boxes, running heads and chapter title. |

## Book files
- `sozlukler/<Book>_sozluk.json` — English → Turkish term glossary per book (`{"book": …, "terms": [{source, target, category, aliases, notes}]}`). Terms marked `uncertain` in `notes` still need review.
- `stiller/<Book>_stil.md` — style sheet per book: abbreviations, units, citation rules, figure labels, chapter/section title translations, source errors found.

The skill reads both at the start of a session and updates them at the end.

## Translation file (`tr.json`)
- body items: `"i001": "text with **bold** markers"`
- captions: `"p16_cap1": ["bold title", "rest of caption"]`
- running heads: `"p17_rh": "..."` (page/chapter numbers are kept automatically)
- chapter title: `"p16_h1": "..."`

## Adapting to a new book
- `extract.py` → `ROLE()` maps font name/size to roles (body, h1, h2, h3, author, caption, running head). Check the fonts first:
  `python3 -c "import pdfplumber;p=pdfplumber.open('book.pdf').pages[N];import collections;print(collections.Counter((c['fontname'],round(c['size'],1)) for c in p.chars).most_common())"`
- `layout.py` → `BODY_SIZE`, `PITCH`, `PARA_INDENT`, `BULLET_INDENT`, heading sizes/colors in `styles()`, column right edges used for captions/title (280.8 / 510.4) — tuned for Thieme 2-column atlases.

Requirements: `pdfplumber`, `pypdf`, `reportlab`, fonts Liberation Serif + Carlito.

Book PDFs and translated text do not belong in this repository (it is public); only scripts, glossaries and style sheets.
