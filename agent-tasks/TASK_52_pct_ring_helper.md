# TASK 52 — Compact percent ring (`pctRing`) for values that exceed 100%

**You: VS Code developer agent.** Front-end only — no DB. Log in `DEV_HANDOFF.md`;
end with `ALL_DONE`. **DO NOT COMMIT/PUSH** — user commits from Windows. Testing is
on-request only.

## Goal

A reusable SVG helper that shows a percentage in a tiny fixed slot (~22px) and
handles values **over 100%** without growing: fill to 100%, then encode the excess
with color + lapping (and an `N×` multiple for very large values).

## Add the helper (`web/_common.js`, or `web/actions.js`)

Expose on `window` like the other shared helpers:

```js
// pctRing(value, opts) -> SVG string. value is in PERCENT units (42 = 42%, 150 = 150%).
// Handles >100% by lapping (deep-green full ring + amber remainder) and, for huge
// values, a solid red ring with an "N×" multiple. null/undefined -> empty track ring.
// If your stored value is a fraction (0.42), pass value*100.
function pctRing(value, opts) {
  opts = opts || {};
  var size  = opts.size  || 22;          // px, the whole glyph
  var sw    = opts.stroke || 3;          // ring thickness
  var track = opts.track || '#eef0f3';   // empty-track color
  var c = size / 2, r = c - sw / 2, C = 2 * Math.PI * r;
  var v = (value == null || isNaN(value)) ? null : Number(value);
  var label = (v == null ? '—' : Math.round(v) + '%');

  var svg = '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+
            '" role="img" aria-label="'+label+'"><title>'+label+'</title>' +
            '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+track+
            '" stroke-width="'+sw+'"/>';
  if (v == null) return svg + '</svg>';

  function arc(frac, color){
    frac = Math.max(0, Math.min(1, frac));
    return '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+color+
           '" stroke-width="'+sw+'" stroke-linecap="round" stroke-dasharray="'+
           (frac*C).toFixed(2)+' '+C.toFixed(2)+'" transform="rotate(-90 '+c+' '+c+')"/>';
  }
  function full(color){
    return '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+color+
           '" stroke-width="'+sw+'"/>';
  }

  var body;
  if (v <= 0)        body = '';                                   // empty (track only)
  else if (v < 100)  body = arc(v/100, '#22c55e');                // green partial
  else if (v === 100)body = full('#15803d');                      // exactly full
  else if (v <= 200) body = full('#15803d') + arc((v-100)/100, '#f59e0b'); // lap1 + amber remainder
  else {                                                          // way over: solid red + N×
    body = full('#dc2626') +
      '<text x="'+c+'" y="'+(c + size*0.15)+'" text-anchor="middle" font-size="'+
      (size*0.4)+'" font-weight="800" fill="#dc2626">'+Math.floor(v/100)+'×</text>';
  }
  return svg + body + '</svg>';
}
window.pctRing = pctRing;
```

## Render rules

- `< 100%` → partial green arc from 12 o'clock, clockwise; fraction = value/100.
- `= 100%` → solid deep-green ring.
- `100–200%` → solid deep-green ring + amber arc for `(value−100)/100`.
- `> 200%` → solid red ring with `N×` in the center (`N = floor(value/100)`).
- `≤ 0` / null → empty track ring.
- Exact value lives in the SVG `<title>` + `aria-label`.

## Usage at the call site

```js
'<td class="num pct-ring-cell" title="'+(r.some_pct==null?'':Math.round(r.some_pct)+'%')+
 '">'+ pctRing(r.some_pct) +'</td>'
// custom size: pctRing(r.some_pct, { size: 18 })
```

```css
.pct-ring-cell { text-align:center; padding:2px 4px; line-height:0; }
```

> Call site / which column: **TBD by the user.** Add the helper now; the exact
> column to apply it to will be specified separately. Pass values in **percent
> units** (multiply fractions by 100 at the call site).

## Notes / edge cases

- Assumes non-negative values. If the target metric can go negative, do NOT guess —
  flag it; the agreed treatment is a red arc of `abs(value)/100` with the sign in
  the tooltip (a ~3-line change).
- Keep `size ≥ 16` so the `N×` text stays legible.

## Acceptance (manual, no tester round)

- `node --check` passes on the changed file.
- A demo row of 25 / 80 / 100 / 150 / 320 renders: green-partial / green-partial /
  full-green / green+amber / red-`3×`.
- Hover shows the exact percent.

## Constraints

Front-end only; no DB/derive/schema. Follow `CLAUDE.md`. No commits/pushes (#17).
Verify the edit isn't truncated (`node --check`).
