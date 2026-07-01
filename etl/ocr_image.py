"""
etl/ocr_image.py — Standalone command-line OCR utility.

Runs the same Tesseract engine used by etl/hedgeye/msr_ocr.py against an
arbitrary local image file and prints the extracted text to stdout.

Usage:
    python -m etl.ocr_image "C:\\path\\to\\image.png"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_TESSERACT = r"C:\Users\chash\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"


def ocr_image(path: str) -> str:
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT
    return pytesseract.image_to_string(Image.open(path))


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert an image to text via Tesseract OCR.")
    ap.add_argument("image", help="Path to the image file")
    args = ap.parse_args()

    if not Path(args.image).exists():
        print(f"File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    print(ocr_image(args.image))


if __name__ == "__main__":
    main()
