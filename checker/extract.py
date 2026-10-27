"""Extract raw per-page text from the approval PDF, auto-detecting text-layer vs scanned."""
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

MIN_TEXT_CHARS = 100  # below this, treat the PDF as a scan needing OCR
OCR_DPI = 300
OCR_DPI_RETRY = 400


@dataclass
class PageText:
    page_no: int
    text: str
    mode: str  # "text" or "ocr"


def _page_count(pdf_path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else 0


def _pdftotext_page(pdf_path: Path, page_no: int) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(page_no), "-l", str(page_no), str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout


def _ocr_page(pdf_path: Path, page_no: int, dpi: int = OCR_DPI, psm: int = 4) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-f", str(page_no), "-l", str(page_no), "-png", str(pdf_path), str(prefix)],
            capture_output=True, check=True,
        )
        pngs = sorted(Path(tmp).glob("page*.png"))
        if not pngs:
            return ""
        result = subprocess.run(
            ["tesseract", str(pngs[0]), "-", "--psm", str(psm), "-l", "eng"],
            capture_output=True, text=True,
        )
        return result.stdout


def extract_pdf(pdf_path: Path) -> tuple[list[PageText], str]:
    """Returns (pages, overall_mode). overall_mode is 'text' or 'ocr'."""
    n_pages = _page_count(pdf_path)
    if n_pages == 0:
        raise ValueError("Could not determine page count (pdfinfo failed or returned no Pages field)")

    # Decide mode by sampling page 1's text layer
    sample = _pdftotext_page(pdf_path, 1)
    overall_mode = "text" if len(sample.strip()) >= MIN_TEXT_CHARS else "ocr"

    pages: list[PageText] = []
    for p in range(1, n_pages + 1):
        if overall_mode == "text":
            text = _pdftotext_page(pdf_path, p) if p > 1 else sample
        else:
            text = _ocr_page(pdf_path, p)
        pages.append(PageText(page_no=p, text=text, mode=overall_mode))
    return pages, overall_mode


def reocr_page(pdf_path: Path, page_no: int) -> str:
    """Fallback re-OCR at higher DPI / different PSM for pages that failed the integrity check."""
    return _ocr_page(pdf_path, page_no, dpi=OCR_DPI_RETRY, psm=4)
