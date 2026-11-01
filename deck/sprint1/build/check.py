"""Programmatic QA: text fit with real Inter metrics, WCAG contrast on known fills, em dash, bounds, banned words."""
import sys, re
from pptx import Presentation
from pptx.util import Emu
from pptx.oxml.ns import qn
from metrics import width_pt, LINE

EMU_IN = 914400
prs = Presentation(sys.argv[1])
SW, SH = prs.slide_width / EMU_IN, prs.slide_height / EMU_IN
DEF_SIZE = 18.0
problems, report = [], []


def run_font(r):
    rPr = r._r.find(qn("a:rPr"))
    fam, size = "Inter", None
    if rPr is not None:
        lat = rPr.find(qn("a:latin"))
        if lat is not None:
            fam = lat.get("typeface")
        if rPr.get("sz"):
            size = int(rPr.get("sz")) / 100
    return fam, size or DEF_SIZE


def para_lines(p, avail_pt):
    """Greedy word wrap; returns (lines, max_size, space_before+after)."""
    runs = []
    for el in p._p:
        if el.tag == qn("a:r"):
            from pptx.text.text import _Run
            rr = _Run(el, p)
            runs.append((rr.text, *run_font(rr)))
        elif el.tag == qn("a:br"):
            runs.append(("\n", None, None))
    if not runs:
        return 1, DEF_SIZE * 0.5, 0
    pPr = p._p.find(qn("a:pPr"))
    indent = 0
    if pPr is not None and pPr.get("marL"):
        indent = int(pPr.get("marL")) / 12700
    avail = avail_pt - indent
    # tokens: split each run into words keeping spaces
    toks = []
    last = ("Inter", DEF_SIZE)
    for text, fam, size in runs:
        if text == "\n" and fam is None:
            toks.append(("\n", None, None)); continue
        last = (fam, size)
        for t in re.findall(r"[^ ]+ *| +", text):
            toks.append((t, fam, size))
    lines, cur = 1, 0.0
    for t, fam, size in toks:
        if fam is None:
            lines += 1; cur = 0.0; continue
        w = width_pt(t, size, fam)[0]
        wt = width_pt(t.rstrip(), size, fam)[0]
        if cur + wt > avail and cur > 0:
            lines += 1
            cur = w
            while cur - (w - wt) > avail:  # single token longer than line
                lines += 1
                cur -= avail
        else:
            cur += w
    maxs = max(s for _, f, s in runs if f is not None)
    sp = 0
    if p.space_after is not None:
        sp += p.space_after.pt
    if p.space_before is not None:
        sp += p.space_before.pt
    ls = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
    return lines, maxs * LINE * ls, sp


def tf_need(tf, w_in):
    bp = tf._txBody.find(qn("a:bodyPr"))
    def ins(k, d):
        v = bp.get(k)
        return int(v) / EMU_IN if v is not None else d
    l, r, t, b = ins("lIns", 0.1), ins("rIns", 0.1), ins("tIns", 0.05), ins("bIns", 0.05)
    avail = (w_in - l - r) * 72
    total, nlines = 0.0, []
    for p in tf.paragraphs:
        n, lh, sp = para_lines(p, avail)
        total += n * lh + sp
        nlines.append(n)
    return total / 72 + t + b, nlines


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    a, b = _lum(a), _lum(b)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def solid_fill(el):
    """srgb of a direct a:solidFill child of spPr / tcPr, or None."""
    for pr in (el.find(qn("p:spPr")), el.find(qn("a:tcPr"))):
        if pr is not None:
            sf = pr.find(qn("a:solidFill"))
            if sf is not None and sf.find(qn("a:srgbClr")) is not None:
                return sf.find(qn("a:srgbClr")).get("val")
    return None


def check_contrast(si, name, txBody, bg):
    """WCAG AA: 4.5 for text < 14 pt (incl. semibold), 3.0 for larger. Only where the fill is known."""
    if bg is None or txBody is None:
        return
    for r in txBody.iter(qn("a:r")):
        rPr = r.find(qn("a:rPr"))
        if rPr is None or not (r.findtext(qn("a:t")) or "").strip():
            continue
        sf = rPr.find(qn("a:solidFill"))
        if sf is None or sf.find(qn("a:srgbClr")) is None:
            continue
        fg = sf.find(qn("a:srgbClr")).get("val")
        size = int(rPr.get("sz", "1800")) / 100
        need = 3.0 if size >= 14 else 4.5
        cr = contrast(fg, bg)
        if cr < need:
            problems.append(f"S{si} '{name}': contrast {cr:.2f} < {need} ({fg} on {bg}, {size} pt): "
                            f"{r.findtext(qn('a:t'))[:30]!r}")


for si, slide in enumerate(prs.slides, 1):
    for sh in slide.shapes:
        if sh.has_text_frame:
            check_contrast(si, sh.name, sh._element.find(qn("p:txBody")), solid_fill(sh._element))
        if sh.has_table:
            for tc in sh._element.iter(qn("a:tc")):
                check_contrast(si, sh.name, tc.find(qn("a:txBody")), solid_fill(tc))

    for sh in slide.shapes:
        x, y = sh.left / EMU_IN, sh.top / EMU_IN
        w, h = sh.width / EMU_IN, sh.height / EMU_IN
        if x < -0.01 or y < -0.01 or x + w > SW + 0.01 or y + h > SH + 0.01:
            problems.append(f"S{si} '{sh.name}': out of slide bounds ({x:.2f},{y:.2f},{w:.2f},{h:.2f})")
        texts = []
        if sh.has_text_frame and sh.text_frame.text.strip():
            need, nl = tf_need(sh.text_frame, w)
            ratio = need / h
            report.append((si, sh.name, round(need, 2), round(h, 2), round(ratio, 2), nl))
            if need > h + 0.01:
                problems.append(f"S{si} '{sh.name}': text needs {need:.2f} in, box {h:.2f} in (lines {nl})")
            texts.append(sh.text_frame.text)
        if sh.has_table:
            tbl = sh.table
            tot = 0
            for ri, row in enumerate(tbl.rows):
                rh = row.height / EMU_IN
                need_row = rh
                for ci, c in enumerate(row.cells):
                    cw = tbl.columns[ci].width / EMU_IN
                    tf = c.text_frame
                    l, r = c.margin_left / EMU_IN, c.margin_right / EMU_IN
                    t, b = c.margin_top / EMU_IN, c.margin_bottom / EMU_IN
                    avail = (cw - l - r) * 72
                    need = t + b
                    for p in tf.paragraphs:
                        n, lh, sp = para_lines(p, avail)
                        need += (n * lh + sp) / 72
                    need_row = max(need_row, need)
                    texts.append(c.text_frame.text)
                if need_row > rh + 0.01:
                    problems.append(f"S{si} table '{sh.name}' row {ri}: grows {rh:.2f} -> {need_row:.2f} in")
                tot += need_row
            if y + tot > SH - 0.05:
                problems.append(f"S{si} table '{sh.name}': real height {tot:.2f} in, bottom {y + tot:.2f} in")
            report.append((si, sh.name + " [table real h]", round(tot, 2), round(h, 2), round(tot / h, 2), []))
        for t in texts:
            if "—" in t:
                problems.append(f"S{si} '{sh.name}': EM DASH in text: {t[:60]!r}")
            for bad in ("революцион", "бесшовн", "ИИ-powered", "AI-powered", "ИИ-юрист", "за 10 секунд"):
                if bad.lower() in t.lower():
                    problems.append(f"S{si} '{sh.name}': banned word {bad!r}")
    if slide.has_notes_slide and "—" in slide.notes_slide.notes_text_frame.text:
        problems.append(f"S{si} notes: EM DASH")

if "-v" in sys.argv:
    for r in report:
        print(r)
print("\n".join(problems) if problems else "NO PROBLEMS")
