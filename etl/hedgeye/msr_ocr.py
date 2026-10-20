"""
MSR chart OCR — process MARKET SITUATION REPORT chart images in-memory.

Downloads each chart URL, runs Tesseract OCR, applies two rules:
  1. "SPX Gamma Exposure" found → save image to msr_dir/MSR YYYY-MM-DD.png
  2. "Gamma Throttle" found → parse Gamma Throttle + 10-Day rVol → hist_msr
  3. The saved SPX Gamma image's 4 top-box lights → hist_msr.*_light (msr_lights.py)

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

from etl.hedgeye.msr_lights import detect_lights, save_lights

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


def save_mktsit_images(urls: list[str], email_date: date, out_dir: str) -> int:
    """Save every chart of this MSR email to out_dir as 'MktSit YYYY-MM-DD NN.<ext>'.

    Only the latest email is kept: an older email never replaces a newer set,
    and a newer (or same-day) email clears the old files first. Nothing is
    deleted unless at least one new image downloaded.
    """
    d = Path(out_dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
        existing = sorted(d.glob("MktSit *"))
        for f in existing:
            try:
                if date.fromisoformat(f.name[7:17]) > email_date:
                    return 0
            except ValueError:
                pass
        got: list[tuple[str, bytes]] = []
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    ctype = resp.headers.get_content_type()
                    data = resp.read()
            except Exception as e:
                log.warning("msr_ocr: mktsit download failed %s: %s", url, e)
                continue
            ext = {"image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}.get(ctype, "png")
            got.append((ext, data))
        if not got:
            return 0
        for f in existing:
            f.unlink()
        for i, (ext, data) in enumerate(got, 1):
            (d / f"MktSit {email_date.isoformat()} {i:02d}.{ext}").write_bytes(data)
        log.info("msr_ocr: %d Mkt Situation images saved -> %s", len(got), d)
        return len(got)
    except Exception as e:
        log.warning("msr_ocr: mktsit save failed: %s", e)
        return 0


def process_msr_images(
    urls: list[str], email_date: date, message_id: str, session, msr_dir: str = ""
) -> dict:
    """OCR each chart in-memory; apply SPX Gamma and Gamma Throttle rules."""
    spx_saved = False
    spx_bytes = b""
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
                spx_bytes = img_bytes
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

    # Some MSR emails omit the Gamma Throttle chart entirely (Hedgeye varies
    # which charts it includes day to day) — OCR retry can't recover a number
    # that was never sent. Still record a stub row keyed to the SPX Gamma
    # chart we DID save, so the Actionable panel's exact-date lookup finds a
    # row and renders the image instead of going blank. ON CONFLICT DO
    # NOTHING so this never clobbers a real gamma_throttle row from a
    # previous or later pass.
    if spx_saved and not gt_done:
        try:
            session.execute(
                text(
                    "INSERT INTO hist_msr "
                    "(snapshot_date, gamma_throttle, rvol_10day, message_id) "
                    "VALUES (:sd, NULL, NULL, :mid) "
                    "ON CONFLICT (snapshot_date) DO NOTHING"
                ),
                {"sd": email_date, "mid": message_id},
            )
            log.info(
                "msr_ocr: hist_msr stub row inserted date=%s (no Gamma Throttle chart in this email)",
                email_date,
            )
        except Exception as e:
            log.warning("msr_ocr: hist_msr stub insert failed: %s", e)

    # Top-box lights (Gamma / Systematic Flow / PV Band / Strategic Allocation):
    # read from the same SPX Gamma image by colour (etl/hedgeye/msr_lights.py).
    # Upserts only the 4 light columns, so it composes with either row above.
    if spx_bytes:
        lights = detect_lights(spx_bytes)
        summary["lights"] = lights
        if lights:
            try:
                save_lights(session, email_date, lights, message_id)
                log.info("msr_ocr: hist_msr lights date=%s %s", email_date, lights)
            except Exception as e:
                log.warning("msr_ocr: hist_msr lights save failed: %s", e)
        else:
            log.warning("msr_ocr: top-box lights not readable for %s", email_date)

    return summary
