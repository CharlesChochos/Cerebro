"""
PDF export — generates PDF intelligence reports from events, briefs,
and analysis data.

Uses a pure-Python PDF generation approach (no external dependencies)
that produces valid PDF 1.4 documents with text, tables, and headers.
"""
import io
import json
from datetime import datetime, timezone


class SimplePDFWriter:
    """Minimal PDF 1.4 writer — text-only, no images, but valid PDF structure."""

    def __init__(self):
        self.objects: list[bytes] = []
        self.pages: list[int] = []
        self.page_contents: list[str] = []

    def _add_object(self, content: bytes) -> int:
        self.objects.append(content)
        return len(self.objects)

    def add_page(self, text_lines: list[str]):
        """Add a page with the given text lines."""
        self.page_contents.append("\n".join(text_lines))

    def render(self) -> bytes:
        """Render to PDF bytes."""
        buf = io.BytesIO()
        offsets = []

        buf.write(b"%PDF-1.4\n")

        # Object 1: Catalog
        offsets.append(buf.tell())
        buf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

        # Object 2: Pages (placeholder, fill after pages known)
        pages_offset = buf.tell()
        offsets.append(pages_offset)

        page_refs = []
        obj_num = 3

        # Create font object
        font_obj = obj_num
        offsets.append(buf.tell())
        buf.write(f"{font_obj} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode())
        obj_num += 1

        # Create each page
        for page_text in self.page_contents:
            # Content stream
            # Escape special PDF characters
            safe_text = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines = safe_text.split("\n")

            stream_parts = [f"BT /F1 10 Tf 50 750 Td 12 TL"]
            for line in lines:
                stream_parts.append(f"({line}) '")
            stream_parts.append("ET")
            stream_content = "\n".join(stream_parts)
            stream_bytes = stream_content.encode("latin-1", errors="replace")

            content_obj = obj_num
            offsets.append(buf.tell())
            buf.write(f"{content_obj} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode())
            buf.write(stream_bytes)
            buf.write(b"\nendstream\nendobj\n")
            obj_num += 1

            page_obj = obj_num
            offsets.append(buf.tell())
            buf.write(
                f"{page_obj} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 612 792] "
                f"/Contents {content_obj} 0 R "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>\n"
                f"endobj\n".encode()
            )
            page_refs.append(f"{page_obj} 0 R")
            obj_num += 1

        # Now write Pages object
        total_objects = obj_num - 1
        pages_content = f"2 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>\nendobj\n"

        # Rewrite the file with correct Pages object
        final = io.BytesIO()
        final.write(b"%PDF-1.4\n")
        new_offsets = []

        # Object 1
        new_offsets.append(final.tell())
        final.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

        # Object 2 (Pages)
        new_offsets.append(final.tell())
        final.write(pages_content.encode())

        # Object 3+ (font, content streams, pages)
        remaining = buf.getvalue()[offsets[1] + len(f"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n".encode()):]
        # Simpler approach: rebuild from scratch
        # Font
        new_offsets.append(final.tell())
        final.write(f"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode())

        obj_n = 4
        for page_text in self.page_contents:
            safe_text = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines = safe_text.split("\n")
            stream_parts = [f"BT /F1 10 Tf 50 750 Td 12 TL"]
            for line in lines:
                stream_parts.append(f"({line}) '")
            stream_parts.append("ET")
            stream_content = "\n".join(stream_parts)
            stream_bytes = stream_content.encode("latin-1", errors="replace")

            new_offsets.append(final.tell())
            final.write(f"{obj_n} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode())
            final.write(stream_bytes)
            final.write(b"\nendstream\nendobj\n")
            obj_n += 1

            new_offsets.append(final.tell())
            final.write(
                f"{obj_n} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 612 792] "
                f"/Contents {obj_n - 1} 0 R "
                f"/Resources << /Font << /F1 3 0 R >> >> >>\n"
                f"endobj\n".encode()
            )
            obj_n += 1

        # Cross-reference table
        xref_offset = final.tell()
        final.write(b"xref\n")
        final.write(f"0 {obj_n}\n".encode())
        final.write(b"0000000000 65535 f \n")
        for off in new_offsets:
            final.write(f"{off:010d} 00000 n \n".encode())

        # Trailer
        final.write(f"trailer\n<< /Size {obj_n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())

        return final.getvalue()


def export_events_pdf(conn, event_ids: list[str] | None = None,
                      category: str | None = None,
                      country_code: str | None = None,
                      limit: int = 50,
                      title: str = "Cerebro Intelligence Report") -> bytes:
    """Export events as a PDF report."""
    conditions, params = [], []
    if event_ids:
        placeholders = ",".join("?" * len(event_ids))
        conditions.append(f"id IN ({placeholders})")
        params.extend(event_ids)
    if category:
        conditions.append("category = ?"); params.append(category)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT id, title, category, severity, source, country_code, timestamp, summary FROM events{where} ORDER BY timestamp DESC LIMIT ?",
        params + [limit]).fetchall()
    events = [dict(r) for r in rows]

    pdf = SimplePDFWriter()

    # Title page
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title_lines = [
        title,
        f"Generated: {now}",
        f"Total Events: {len(events)}",
        "",
        "CLASSIFICATION: UNCLASSIFIED",
        "=" * 60,
    ]
    if category:
        title_lines.append(f"Category Filter: {category}")
    if country_code:
        title_lines.append(f"Country Filter: {country_code}")
    pdf.add_page(title_lines)

    # Event pages (batch events per page)
    batch_size = 8
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        lines = [f"Events {i + 1}-{min(i + batch_size, len(events))} of {len(events)}", ""]
        for e in batch:
            sev_label = "HIGH" if e["severity"] >= 70 else "MED" if e["severity"] >= 40 else "LOW"
            lines.extend([
                f"[{sev_label}] {e['title'][:80]}",
                f"  Category: {e['category'] or 'N/A'} | Source: {e['source']} | Country: {e['country_code'] or 'N/A'}",
                f"  Severity: {e['severity']:.0f} | Time: {e['timestamp'][:19]}",
                f"  {(e['summary'] or '')[:120]}",
                "-" * 60,
            ])
        pdf.add_page(lines)

    return pdf.render()


def export_brief_pdf(conn, brief_id: str) -> bytes | None:
    """Export a single intelligence brief as PDF."""
    row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not row:
        return None

    brief = dict(row)
    pdf = SimplePDFWriter()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "INTELLIGENCE BRIEF",
        "=" * 60,
        f"Generated: {now}",
        f"Brief ID: {brief['id']}",
        f"Type: {brief.get('brief_type', 'N/A')}",
        f"Created: {brief.get('created_at', 'N/A')}",
        "",
        "CONTENT:",
        "-" * 60,
    ]

    content = brief.get("content") or brief.get("summary") or "No content available"
    # Split long content into lines
    words = content.split()
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > 80:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        lines.append(line)

    pdf.add_page(lines)
    return pdf.render()
