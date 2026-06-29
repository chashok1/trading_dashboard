"""
MSR chart OCR — process MARKET SITUATION REPORT chart images in-memory.

Downloads each chart URL, runs Tesseract OCR, applies two rules:
  1. "SPX Gamma Exposure" found → save image to msr_dir/MSR YYYY-MM-DD.png
  2. "Gamma Throttle" found → parse Gamma Throttle + 10-Day rVol → hist_msr

Rolling 30-day archive: images older than 30 days are deleted automatically.
No images written to hedgeye_charts; no hist_media entries created.
"""
from __future__ import annotations

import io
import logging
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

log = logging.getLogger("hedgeye.msr_ocr")

_TESSERACT = r"C:\Users\chash\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

_GT_RE = re.compile(r"Gamma\s+Throttle[:\s]+(-?[\d.]+)", re.IGNORECASE)
_RV_RE = re.compile(r"10[- ]Day\s+rVol[:\s]+(-?[\d.]+)", re.IGNORECASE)


def _ocr(img_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT
        return pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)))
    except Exception as e:
        log.warning("msr_ocr: OCR failed: %s", e)
        return ""


def _cleanup_old(msr_dir: str, days: int = 30) -> None:
    """Delete MSR images whose filename date is older than `days` days."""
    cutoff = date.today() - timedelta(days=days)
    try:
        for f in Path(msr_dir).glob("MSR *.png"):
            try:
                d = date.fromisoformat(f.stem[4:])   # "MSR 2026-06-29" -> "2026-06-29"
                if d < cutoff:
                    f.unlink()
                    log.info("msr_ocr: deleted old MSR %s", f.name)
            except (ValueError, OSError):
                pass
    except Exception as e:
        log.warning("msr_ocr: cleanup failed: %s", e)


def process_msr_images(
    urls: list[str], email_date: date, message_id: str, session, msr_dir: str = ""
) -> dict:
    """OCR each chart in-memory; apply SPX Gamma and Gamma Throttle rules."""
    spx_saved = False
    gt_done = False
    summary: dict = {"spx_gamma_saved": False, "gamma_throttle": None, "rvol_10day": None}

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                img_bytes = resp.read()
        except Exception as e:
            log.warning("msr_ocr: download failed %s: %s", url, e)
            continue

        ocr_text = _ocr(img_bytes)

        if not spx_saved and "SPX Gamma Exposure" in ocr_text:
            try:
                out_dir = Path(msr_dir) if msr_dir else Path(".")
                out_dir.mkdir(parents=True, exist_ok=True)
                dest = out_dir / f"MSR {email_date.isoformat()}.png"
                dest.write_bytes(img_bytes)
                spx_saved = True
                summary["spx_gamma_saved"] = True
                log.info("msr_ocr: SPX Gamma chart saved -> %s", dest)
                _cleanup_old(str(out_dir))
            except Exception as e:
                log.warning("msr_ocr: failed to save SPX Gamma chart: %s", e)

        if not gt_done and "Gamma Throttle" in ocr_text:
            gm = _GT_RE.search(ocr_text)
            rm = _RV_RE.search(ocr_text)
            if gm:
                gt = float(gm.group(1))
                rv = float(rm.group(1)) if rm else None
                summary["gamma_throttle"] = gt
                summary["rvol_10day"] = rv
                try:
                    session.execute(
                        text(
                            "INSERT INTO hist_msr "
                            "(snapshot_date, gamma_throttle, rvol_10day, message_id) "
                            "VALUES (:sd, :gt, :rv, :mid) "
                            "ON CONFLICT (snapshot_date) DO UPDATE SET "
                            "gamma_throttle=EXCLUDED.gamma_throttle, "
                            "rvol_10day=EXCLUDED.rvol_10day, "
                            "message_id=EXCLUDED.message_id"
                        ),
                        {"sd": email_date, "gt": gt, "rv": rv, "mid": message_id},
                    )
                    gt_done = True
                    log.info(
                        "msr_ocr: hist_msr inserted date=%s gt=%.2f rv=%s",
                        email_date, gt, rv,
                    )
                except Exception as e:
                    log.warning("msr_ocr: hist_msr insert failed: %s", e)

        if spx_saved and gt_done:
            break

    return summary
