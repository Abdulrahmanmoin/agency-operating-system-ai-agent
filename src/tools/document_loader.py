"""Load meeting material (notes/transcripts) from txt / md / docx / pdf into plain text."""

from pathlib import Path

_PLAINTEXT = {".txt", ".md", ".text", ""}


def load_document(path: str | Path) -> str:
    """Return the text content of a notes/transcript file.

    Supports plain text, Markdown, Word (.docx), and PDF. Raises ValueError for unknown types.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in _PLAINTEXT:
        return p.read_text(encoding="utf-8")

    if suffix == ".docx":
        import docx  # python-docx

        document = docx.Document(str(p))
        return "\n".join(para.text for para in document.paragraphs)

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    raise ValueError(f"Unsupported document type: {suffix!r} ({p})")
