"""MSR top-box lights: which cell is lit in each of the 4 rows (pure image logic, no DB)."""
import io

from PIL import Image, ImageDraw, ImageFont

from etl.hedgeye.msr_lights import LIGHT_LABELS, LIGHT_ROWS, detect_lights

GREEN, AMBER, RED = (0, 128, 0), (240, 170, 60), (255, 0, 0)


def _png(lit, width=1800, border=True, col_x=(560, 930, 1300)):
    """Synthetic 4-row box: label on the left, 3 cells, the cell index in `lit` coloured, the rest grey text."""
    h = int(width * 0.19)
    im = Image.new("RGB", (width, h), "white")
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=36)   # real report text is large; the tiny default font is under the cluster-size floor
    cw, rh = col_x[1] - col_x[0], int(h * 0.14)
    for r, key in enumerate(LIGHT_ROWS):
        cy = int(h * (0.18 + 0.23 * r))
        d.text((int(width * 0.08), cy - 18), "Row label here:", fill="black", font=font)
        for c in range(3):
            x0, x1 = col_x[c], col_x[c] + cw
            txt = LIGHT_LABELS[key][c]
            if lit[r] == c:
                d.rectangle([x0, cy - rh // 2, x1, cy + rh // 2], fill=(GREEN, AMBER, RED)[c])
                d.text((x0 + cw // 2 - 50, cy - 18), txt, fill="black", font=font)
            else:
                d.text((x0 + cw // 2 - 50, cy - 18), txt, fill=(128, 128, 128), font=font)
    if border:
        d.rectangle([4, 4, width - 5, h - 5], outline="black", width=2)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_reads_each_row_independently():
    got = detect_lights(_png((2, 2, 0, 0)))
    assert got == {"gamma_light": "Negative", "flow_light": "Bearish",
                   "pv_light": "Long", "alloc_light": "Risk On"}


def test_middle_cell_is_neutral_on_every_row():
    got = detect_lights(_png((1, 1, 1, 1)))
    assert set(got.values()) == {"Neutral"}


def test_works_without_border_and_with_other_column_positions():
    got = detect_lights(_png((0, 1, 2, 1), width=1700, border=False, col_x=(500, 900, 1300)))
    assert got == {"gamma_light": "Positive", "flow_light": "Neutral",
                   "pv_light": "Short", "alloc_light": "Neutral"}


def test_unreadable_image_returns_none():
    assert detect_lights(b"not an image") is None
    blank = io.BytesIO()
    Image.new("RGB", (800, 150), "white").save(blank, "PNG")
    assert detect_lights(blank.getvalue()) is None
