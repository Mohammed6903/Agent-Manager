"""Document → markdown extraction for the manual-context upload path.

Supports **PDF** and **DOCX** uploads. DOCX is handled via ``python-docx``
(XML-based, no OCR needed, zero ambiguity about structure). PDF uses
two backends selected by the ``use_ocr`` flag:

1. **Local (non-OCR)** — uses ``pdfplumber`` (MIT, pure Python, ~3 MB)
   plus a small custom converter that reconstructs structured markdown
   from pdfplumber's per-character font and position metadata:

   - Headings detected via font-size ratio against the page's median
     body-text size (``>=1.5x → #``, ``>=1.25x → ##``, ``>=1.1x
     or bold → ###``)
   - Bullet lists detected by leading glyphs (``•``, ``-``, ``*``, ``○``, ``▪``)
   - Numbered lists detected by ``N.`` / ``N)`` / ``(N)`` patterns
   - Tables extracted via pdfplumber's native ``extract_tables()``,
     formatted as pipe-delimited markdown, with the table regions
     masked so we don't double-include them in the text pass
   - Paragraphs formed from consecutive same-font lines with small
     vertical gaps; larger gaps become ``\\n\\n`` breaks
   - Pages separated by ``\\n\\n---\\n\\n`` so the Notion-style editor
     renders visible page dividers

   No ML models, no torch, no CUDA, no cold start. Works on a 4 GB
   RAM server without breaking a sweat.

2. **Mistral OCR** — POSTs the PDF bytes to Mistral's ``/v1/ocr`` endpoint
   (``mistral-ocr-latest``). Handles scanned documents, math, complex
   tables, multi-column reading order, and anything image-based that
   the local path can't see. Costs ~$0.001-0.002/page; free tier is
   usually sufficient for interactive manual uploads.

The service returns a unified ``PdfExtractionResult`` regardless of
which backend ran, so the router doesn't need to branch.

## Heuristic: "does this PDF probably need OCR?"

Only applied on the local (non-OCR) path. Three signals in decreasing
order of reliability — first hit wins:

1. **Zero extractable text** (smoking gun) — if pdfplumber yields
   literally zero characters across every page, the PDF has no
   embedded text layer at all. Binary test, no false positives.

2. **Per-page text coverage ratio** — count pages with < 50 chars.
   If more than half the pages are empty, the doc is probably a
   mix-mode scan.

3. **Chars-per-page fallback** — total chars / page count < 300 means
   the doc is text-based but suspiciously sparse. Weakest signal.

Thresholds are surfaced as module constants for easy tuning.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import statistics
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ── Heuristic thresholds ────────────────────────────────────────────────────
EMPTY_PAGE_CHAR_CUTOFF = 50
EMPTY_PAGE_RATIO_THRESHOLD = 0.5
FALLBACK_CHARS_PER_PAGE_THRESHOLD = 300

# ── Markdown converter tuning ───────────────────────────────────────────────
# Heading detection: a line whose font size exceeds the page's median
# body-text size by this ratio becomes a markdown heading. Tiers:
#   - ratio >= 1.5  → "# " (H1 — typically title/chapter)
#   - ratio >= 1.25 → "## " (H2 — typically section)
#   - ratio >= 1.10 + bold → "### " (H3 — subsection; we require bold
#     because a 10% size bump alone is too noisy to call a heading)
# Tuning note: raise HEADING_H1_RATIO if your documents over-promote
# emphasised body text; lower it if headings are being missed.
HEADING_H1_RATIO = 1.5
HEADING_H2_RATIO = 1.25
HEADING_H3_RATIO = 1.1

# Bullet-marker glyphs recognized at the start of a line. The ASCII dash
# is included for documents that already use markdown-style bullets.
_BULLET_MARKERS = ("•", "○", "▪", "●", "◦", "–", "—", "-", "*")
# Numbered-list patterns: "1.", "1)", "(1)", "1 -" at line start.
_NUMBERED_LIST_RE = re.compile(r"^\s*(\(?\d+[\.\)])\s+")
# Bullet-list patterns: any of the markers above followed by whitespace.
_BULLET_LIST_RE = re.compile(
    r"^\s*([" + re.escape("".join(_BULLET_MARKERS)) + r"])\s+"
)

# ── Mistral OCR API ─────────────────────────────────────────────────────────
_MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
_MISTRAL_OCR_MODEL = "mistral-ocr-latest"
# Generous read timeout because OCR on a large / complex / non-Latin
# page (Devanagari, CJK, Arabic) can legitimately take 60-180 seconds
# on Mistral's free tier. A 5-minute cap is the upper bound for an
# interactive upload — beyond that, the user would reasonably assume
# something's wrong anyway. Connect timeout stays moderate because the
# initial TLS + POST handshake is fast once reached.
_OCR_TIMEOUT = httpx.Timeout(300.0, connect=15.0)


# ── Result + error types ────────────────────────────────────────────────────


@dataclass
class DocumentExtractionResult:
    """Output of any extraction path (PDF or DOCX). The router turns
    this into an ``UploadDocumentResponse`` (plus the created
    ``GlobalContext``) for the HTTP response.

    ``source_format`` is "pdf" or "docx". ``page_count`` is always 1
    for DOCX since the format doesn't have a meaningful page concept
    for content extraction — docx uses explicit section breaks that
    don't correspond to display pages the way PDFs do. ``used_ocr``
    and ``warning`` are always ``False``/``None`` for DOCX because
    DOCX is XML-based and always has real text.
    """

    markdown: str
    page_count: int
    char_count: int
    used_ocr: bool
    warning: Optional[str]
    source_format: str  # "pdf" | "docx"


# Backwards-compat alias. Existing callers that still import
# ``PdfExtractionResult`` keep working; new code uses the generic name.
PdfExtractionResult = DocumentExtractionResult


class DocumentExtractionError(Exception):
    """Generic downstream failure (Mistral/pdfplumber/python-docx crash,
    timeout, upstream outage). Router maps to HTTP 502."""


class InvalidDocumentError(DocumentExtractionError):
    """The uploaded bytes are not a parseable PDF or DOCX at all
    (encrypted, corrupted, XFA-only, legacy .doc binary format, wrong
    file type). Router maps to HTTP 400 so the client gets a clear
    "your file is invalid" response rather than a generic
    "extraction failed" message."""


# Backwards-compat aliases — keep the PDF-specific error names callable
# so old test code / scripts don't break. New callers should use the
# generic names above.
PdfExtractionError = DocumentExtractionError
InvalidPdfError = InvalidDocumentError


# ── OCR-need detector (local path only) ─────────────────────────────────────


def _detect_ocr_need(
    pdf_bytes: bytes,
) -> tuple[int, int, Optional[str]]:
    """Analyze a PDF to decide if it probably needs OCR.

    Returns ``(page_count, total_extracted_chars, warning_or_None)``.
    Raises ``InvalidPdfError`` when pdfplumber can't open the file,
    so the router maps the failure to HTTP 400 instead of 502.

    Uses pdfplumber (same library as the extraction backend, so a
    single import for both) and its per-page ``extract_text`` method.
    pdfplumber is pure-Python and opens via an in-memory bytes buffer,
    so there's no disk round-trip.
    """
    import pdfplumber  # noqa: PLC0415

    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.warning("pdfplumber failed to open PDF: %s", exc)
        raise InvalidPdfError(
            "The uploaded file is not a valid PDF or is encrypted / "
            "corrupted / form-only. The PDF parser reported: "
            f"{exc}. If the file opens correctly in a PDF viewer, it "
            "may use an XFA form layer or an unsupported encryption "
            "scheme — re-export it to a standard PDF and try again, "
            "or re-upload with the OCR option enabled."
        ) from exc

    try:
        total_pages = len(pdf.pages)
        if total_pages == 0:
            return 0, 0, None

        page_char_counts: list[int] = []
        for page in pdf.pages:
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                # Individual page extraction can fail on a malformed
                # page without invalidating the whole document; treat
                # as "empty" and let the ratio signal catch it.
                text = ""
            page_char_counts.append(len(text))

        total_chars = sum(page_char_counts)

        # Signal 1: zero extractable text anywhere → definitely scanned.
        if total_chars == 0:
            return (
                total_pages,
                0,
                (
                    f"No selectable text was found anywhere in this "
                    f"{total_pages}-page document. The PDF appears to "
                    f"consist entirely of page images rather than "
                    f"embedded text, so its contents cannot be captured "
                    f"through the standard extraction path. Re-upload "
                    f"this file with the OCR option enabled to recover "
                    f"its contents."
                ),
            )

        # Signal 2: per-page empty ratio.
        empty_pages = sum(
            1 for c in page_char_counts if c < EMPTY_PAGE_CHAR_CUTOFF
        )
        empty_ratio = empty_pages / total_pages

        if empty_ratio > EMPTY_PAGE_RATIO_THRESHOLD:
            return (
                total_pages,
                total_chars,
                (
                    f"The PDF was imported, but {empty_pages} of "
                    f"{total_pages} pages contain little or no "
                    f"extractable text. This typically indicates scanned "
                    f"or image-based pages whose contents can only be "
                    f"recovered with optical character recognition. If "
                    f"the stored context looks incomplete, re-upload "
                    f"this file with the OCR option enabled."
                ),
            )

        # Signal 3: chars-per-page fallback.
        chars_per_page = total_chars / total_pages
        if chars_per_page < FALLBACK_CHARS_PER_PAGE_THRESHOLD:
            return (
                total_pages,
                total_chars,
                (
                    f"The PDF was imported, but the recovered text "
                    f"density (~{chars_per_page:.0f} characters per "
                    f"page across {total_pages} pages) is notably below "
                    f"the typical range for text-based documents. Some "
                    f"pages may contain scanned or image-embedded "
                    f"content that the standard text path cannot read. "
                    f"If the stored context looks incomplete, re-upload "
                    f"with the OCR option enabled."
                ),
            )

        return total_pages, total_chars, None
    finally:
        pdf.close()


# ── Local (non-OCR) extraction: pdfplumber + markdown converter ─────────────


def _line_has_bold_font(line: dict) -> bool:
    """Best-effort 'is this line bold' check.

    pdfplumber exposes per-character font names; we consider a line
    bold if any character on it has 'bold' in its font name. This
    misses some fonts that encode weight differently but catches the
    common case (Helvetica-Bold, Arial,Bold, TimesNewRomanPS-BoldMT).
    """
    chars = line.get("chars") or []
    for c in chars:
        name = (c.get("fontname") or "").lower()
        if "bold" in name or "black" in name or "heavy" in name:
            return True
    return False


def _group_chars_into_lines(page) -> list[dict]:
    """Group pdfplumber's per-character output into line-level dicts.

    pdfplumber gives us ``page.chars`` as a flat list of character
    records; for markdown reconstruction we need lines, not characters.
    We bucket characters into lines using their ``top`` coordinate —
    characters with the same ``top`` (within a small tolerance) belong
    to the same line.

    Returns a list of ``{text, size, top, chars}`` dicts, ordered
    top-to-bottom.
    """
    chars = page.chars or []
    if not chars:
        return []

    # Sort by vertical position, then horizontal so line order and
    # character order within each line are both natural reading order.
    chars = sorted(chars, key=lambda c: (round(c.get("top") or 0, 1), c.get("x0") or 0))

    lines: list[dict] = []
    current_top: Optional[float] = None
    current_chars: list[dict] = []
    # Tolerance for grouping chars into the same line. 3pt covers
    # normal leading variation without merging adjacent paragraphs.
    LINE_TOLERANCE = 3.0

    for ch in chars:
        top = ch.get("top") or 0
        if current_top is None or abs(top - current_top) <= LINE_TOLERANCE:
            current_chars.append(ch)
            if current_top is None:
                current_top = top
        else:
            if current_chars:
                lines.append(_finalize_line(current_chars, current_top))
            current_chars = [ch]
            current_top = top

    if current_chars:
        lines.append(_finalize_line(current_chars, current_top or 0))

    return lines


def _finalize_line(chars: list[dict], top: float) -> dict:
    """Turn a list of character dicts into a line record."""
    # Reconstruct the text by joining characters in x-order with no
    # padding — pdfplumber's char records already include spaces where
    # appropriate.
    chars_in_order = sorted(chars, key=lambda c: c.get("x0") or 0)
    text = "".join((c.get("text") or "") for c in chars_in_order)
    sizes = [float(c.get("size") or 0) for c in chars_in_order if c.get("size")]
    size = statistics.median(sizes) if sizes else 0.0
    return {
        "text": text.rstrip(),
        "size": size,
        "top": top,
        "chars": chars_in_order,
    }


def _is_plausible_table(rows: list[list[Any]]) -> bool:
    """Sanity filter for pdfplumber's table detector.

    pdfplumber's ``find_tables()`` fires on any grid-ish layout, which
    produces lots of false positives on slide decks, title pages, and
    single-column content where text happens to line up. We reject
    anything that doesn't look like a real table:

    - **Fewer than 2 rows** → not a table, it's a single-line layout
    - **Fewer than 2 columns** → not a table, it's a bulleted list
      pretending to be one
    - **Fewer than 3 non-empty cells total** → not enough content to
      be meaningful as a table
    - **Only one column has any content** → pdfplumber split a
      single-column layout into columns based on alignment noise

    When the filter rejects a table, the caller falls through to the
    regular text-extraction path, which handles the content as a
    paragraph or list — better output than ``| Col 1 |`` wrapping
    arbitrary text.
    """
    if not rows or len(rows) < 2:
        return False
    if not rows[0] or len(rows[0]) < 2:
        return False

    non_empty_count = 0
    cols_with_content: set[int] = set()
    for row in rows:
        for col_idx, cell in enumerate(row):
            if cell is not None and str(cell).strip():
                non_empty_count += 1
                cols_with_content.add(col_idx)

    if non_empty_count < 3:
        return False
    if len(cols_with_content) < 2:
        return False
    return True


def _extract_tables_as_markdown(page) -> tuple[list[str], list[tuple[float, float, float, float]]]:
    """Pull tables out of a page, format each as a markdown pipe table,
    and return the bounding boxes of extracted tables so the text pass
    can skip characters that fall inside them (avoiding double-include).

    Only tables that pass ``_is_plausible_table`` are kept — this
    filter suppresses pdfplumber's false-positive "table" detection on
    slide decks and single-column content.

    Returns ``(markdown_tables, bbox_list)`` where each bbox is
    ``(x0, top, x1, bottom)`` in pdfplumber coordinates.
    """
    try:
        tables = page.find_tables() or []
    except Exception:
        return [], []

    rendered: list[str] = []
    bboxes: list[tuple[float, float, float, float]] = []

    for table in tables:
        try:
            rows = table.extract() or []
        except Exception:
            continue
        # Drop any table that doesn't look like a real table. The
        # characters that live inside its (rejected) bounding box will
        # then be picked up by the text pass in the normal way.
        if not _is_plausible_table(rows):
            continue

        header = [(c or "").strip() for c in rows[0]]
        body = rows[1:]
        if not any(header):
            header = [f"Col {i+1}" for i in range(len(rows[0]))]
            body = rows

        def _md_row(cells: list[Any]) -> str:
            return "| " + " | ".join(
                (str(c or "").replace("\n", " ").replace("|", "\\|").strip() or " ")
                for c in cells
            ) + " |"

        lines = [_md_row(header), "| " + " | ".join(["---"] * len(header)) + " |"]
        for row in body:
            lines.append(_md_row(row))

        rendered.append("\n".join(lines))
        bboxes.append(tuple(table.bbox))  # type: ignore[arg-type]

    return rendered, bboxes


def _char_in_any_bbox(
    char: dict, bboxes: list[tuple[float, float, float, float]]
) -> bool:
    """Return True if a character's position falls inside any bounding box."""
    x = char.get("x0") or 0
    y = char.get("top") or 0
    for x0, top, x1, bottom in bboxes:
        if x0 <= x <= x1 and top <= y <= bottom:
            return True
    return False


def _classify_line(line: dict, median_size: float) -> str:
    """Turn one line dict into a markdown string.

    Classification priority:
    1. List bullet (``• item``)   → ``- item``
    2. Numbered list (``1. item``) → ``1. item``
    3. Heading by font size        → ``# / ## / ###``
    4. Plain paragraph line        → as-is
    """
    text = line["text"].strip()
    if not text:
        return ""

    # List markers — check these first because a large bold bullet
    # shouldn't be mistaken for a heading.
    m = _BULLET_LIST_RE.match(text)
    if m:
        body = text[m.end():].strip()
        return f"- {body}" if body else "-"

    m = _NUMBERED_LIST_RE.match(text)
    if m:
        body = text[m.end():].strip()
        # Normalize the marker to "N." form for consistent markdown.
        raw = m.group(1).rstrip(")").lstrip("(")
        return f"{raw}. {body}" if body else f"{raw}."

    # Heading detection via font-size ratio against the page median.
    size = line.get("size") or 0
    if median_size > 0 and size > 0:
        ratio = size / median_size
        if ratio >= HEADING_H1_RATIO:
            return f"# {text}"
        if ratio >= HEADING_H2_RATIO:
            return f"## {text}"
        if ratio >= HEADING_H3_RATIO and _line_has_bold_font(line):
            return f"### {text}"

    # Plain body text.
    return text


def _pdf_page_to_markdown(page) -> str:
    """Convert a single pdfplumber page to structured markdown.

    Workflow:
    1. Extract tables first and remember their bounding boxes.
    2. Group the remaining characters into lines (skipping any that
       fall inside a table bbox to prevent double-inclusion).
    3. Compute the page's median body-text font size so the heading
       classifier has a baseline to compare against.
    4. Classify each line and join them. Consecutive paragraph lines
       (neither heading, nor list, nor blank) are merged into a single
       block with a single space between them; blank gaps become
       paragraph breaks.
    5. Append the table markdown after the text content — pdfplumber
       tables don't carry exact insertion positions, so we put them at
       the end of the page rather than trying to interleave them.
    """
    tables, table_bboxes = _extract_tables_as_markdown(page)

    # Characters outside any table bbox
    filtered_chars = [
        c for c in (page.chars or []) if not _char_in_any_bbox(c, table_bboxes)
    ]
    if not filtered_chars and not tables:
        return ""

    # Recreate a pseudo-page object with the filtered chars for line
    # grouping. We shadow ``page.chars`` via a duck-typed dict because
    # _group_chars_into_lines only touches .chars.
    class _PageView:
        chars = filtered_chars

    lines = _group_chars_into_lines(_PageView())

    # Compute median body-text size across lines that look like body
    # text (not table, not obvious heading). Simpler: take the median
    # of all line sizes, since headings are a minority.
    all_sizes = [l["size"] for l in lines if l["size"] > 0]
    median_size = statistics.median(all_sizes) if all_sizes else 0.0

    # Classify and coalesce.
    blocks: list[str] = []
    paragraph_buffer: list[str] = []

    def _flush_paragraph():
        if paragraph_buffer:
            # Join with single space — most PDFs break paragraphs across
            # many short lines, and joining gives readable prose.
            blocks.append(" ".join(paragraph_buffer).strip())
            paragraph_buffer.clear()

    prev_top = None
    prev_size = None
    PARAGRAPH_GAP = 1.8  # multiple of line height — larger gap = new paragraph

    for line in lines:
        rendered = _classify_line(line, median_size)
        if not rendered:
            _flush_paragraph()
            continue

        # A heading or list item ends any in-progress paragraph.
        is_structured = (
            rendered.startswith("#")
            or rendered.startswith("- ")
            or rendered.startswith("-\n")
            or _NUMBERED_LIST_RE.match(rendered) is not None
        )

        # Detect paragraph-break by vertical gap.
        if prev_top is not None and prev_size:
            gap = (line["top"] - prev_top) / max(prev_size, 1.0)
            if gap > PARAGRAPH_GAP:
                _flush_paragraph()

        if is_structured:
            _flush_paragraph()
            blocks.append(rendered)
        else:
            paragraph_buffer.append(rendered)

        prev_top = line["top"]
        prev_size = line["size"]

    _flush_paragraph()

    if tables:
        blocks.extend(tables)

    return "\n\n".join(b for b in blocks if b).strip()


def _extract_without_ocr_sync(pdf_bytes: bytes) -> PdfExtractionResult:
    """Synchronous pdfplumber-based extraction path.

    Runs the heuristic first (inside ``_detect_ocr_need``), then the
    page-by-page markdown conversion. Wrapped in ``run_in_executor``
    from the async entry point so the FastAPI event loop isn't blocked
    while pdfplumber crunches through a large document.
    """
    # Front-door validity check + heuristic. Raises InvalidPdfError
    # if the file isn't a parseable PDF at all.
    page_count_h, char_count_h, warning = _detect_ocr_need(pdf_bytes)

    import pdfplumber  # noqa: PLC0415

    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:
        # Should never happen since _detect_ocr_need already opened
        # it successfully, but defensive in case the heuristic path
        # closes and the re-open races in some unlikely way.
        raise InvalidPdfError(f"Failed to re-open PDF for extraction: {exc}") from exc

    try:
        page_markdowns: list[str] = []
        for page in pdf.pages:
            try:
                md = _pdf_page_to_markdown(page)
            except Exception:
                logger.exception(
                    "Per-page markdown conversion failed; falling back to plain text"
                )
                # Graceful fallback: if the markdown converter trips on
                # a weird page, use pdfplumber's plain-text output for
                # that page rather than dropping it entirely.
                try:
                    md = (page.extract_text() or "").strip()
                except Exception:
                    md = ""
            if md:
                page_markdowns.append(md)

        total_pages = len(pdf.pages)
    finally:
        pdf.close()

    # Join pages with an explicit horizontal rule so the Notion-style
    # editor renders a visible page divider.
    markdown = "\n\n---\n\n".join(page_markdowns)
    char_count = len(markdown)

    logger.info(
        "PDF extract (local): pages=%d chars=%d warning=%s",
        total_pages,
        char_count,
        "yes" if warning else "no",
    )

    return DocumentExtractionResult(
        markdown=markdown,
        page_count=total_pages or page_count_h or 1,
        char_count=char_count,
        used_ocr=False,
        warning=warning,
        source_format="pdf",
    )


# ── Mistral OCR extraction (unchanged) ──────────────────────────────────────


async def _extract_with_ocr(pdf_bytes: bytes) -> PdfExtractionResult:
    """Send the PDF to Mistral OCR and collect the per-page markdown.

    Mistral's OCR endpoint accepts a document by URL or by base64-inlined
    bytes in the request body. We use the inline path so the router
    doesn't have to upload to an intermediate host first.

    The response shape (as of mistral-ocr-2512) is::

        {"pages": [{"index": 0, "markdown": "...", "images": [...]}, ...]}

    We join the per-page markdown with ``\\n\\n---\\n\\n`` so the editor
    renders an explicit horizontal-rule page break. Mistral embeds image
    references in its output as ``![img-N.jpeg](img-N.jpeg)`` — we strip
    those since we don't re-host the images, and leaving them would
    produce broken links in the Notion-style editor.
    """
    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise PdfExtractionError(
            "MISTRAL_API_KEY is not configured — OCR extraction is unavailable"
        )

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    body = {
        "model": _MISTRAL_OCR_MODEL,
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64}",
        },
        "include_image_base64": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_OCR_TIMEOUT) as client:
            resp = await client.post(_MISTRAL_OCR_URL, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise PdfExtractionError(
            f"Mistral OCR timed out after {_OCR_TIMEOUT.read}s"
        ) from exc
    except httpx.TransportError as exc:
        raise PdfExtractionError(f"Mistral OCR network error: {exc}") from exc

    if resp.status_code >= 400:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text[:500]
        raise PdfExtractionError(
            f"Mistral OCR HTTP {resp.status_code}: {err_body}"
        )

    payload = resp.json()
    pages = payload.get("pages") or []
    if not pages:
        raise PdfExtractionError("Mistral OCR returned no pages")

    _image_ref_re = re.compile(r"!\[[^\]]*\]\([^)]+\)")
    cleaned_pages: list[str] = []
    for page in pages:
        md = (page.get("markdown") or "").strip()
        if not md:
            continue
        md = _image_ref_re.sub("", md).strip()
        if md:
            cleaned_pages.append(md)

    if not cleaned_pages:
        raise PdfExtractionError(
            "Mistral OCR returned pages but no extractable markdown"
        )

    markdown = "\n\n---\n\n".join(cleaned_pages)

    logger.info(
        "PDF extract (OCR): pages=%d chars=%d",
        len(pages),
        len(markdown),
    )

    return DocumentExtractionResult(
        markdown=markdown,
        page_count=len(pages),
        char_count=len(markdown),
        used_ocr=True,
        warning=None,
        source_format="pdf",
    )


# ── Public entry point ──────────────────────────────────────────────────────


async def extract_pdf(
    pdf_bytes: bytes,
    *,
    use_ocr: bool = False,
) -> PdfExtractionResult:
    """Extract a PDF to markdown, optionally using Mistral OCR.

    ``use_ocr=False`` (default) runs the local pdfplumber path and
    emits a warning if heuristics suggest the PDF is probably scanned.
    ``use_ocr=True`` calls Mistral OCR directly — no warning is ever
    emitted on the OCR path because OCR either works or fails loudly.

    Raises ``InvalidPdfError`` (HTTP 400) for unparseable files and
    ``PdfExtractionError`` (HTTP 502) for downstream/provider failures.
    """
    if not pdf_bytes:
        raise PdfExtractionError("Empty PDF payload")

    if use_ocr:
        return await _extract_with_ocr(pdf_bytes)

    # Local path is synchronous (pdfplumber + numpy-free heuristics).
    # Offload to a worker thread so the event loop stays responsive.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract_without_ocr_sync, pdf_bytes)
