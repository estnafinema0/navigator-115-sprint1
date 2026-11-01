"""Helpers for building the Navigator-115 deck on the official contest template (python-pptx)."""
import os
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "tplx", "ppt", "media", "image1.png")


def use_template_logo(template_path):
    """Take the VTB + FU logo strip (ppt/media/image1.png) straight from the official template."""
    import io, zipfile
    global LOGO
    with zipfile.ZipFile(template_path) as z:
        LOGO = io.BytesIO(z.read("ppt/media/image1.png"))

TXT, ACC, CARD, BLUE, MUTED, WHITE, TINT, GREY = (
    "434343", "0A86E0", "F4F4F4", "CFE9FE", "5E5E5E", "FFFFFF", "E9F5FE", "C9CDD2")
# template accent #0A86E0 has contrast 3.0-3.8 on the light fills: fine for large text only (>= 14 pt).
# Smaller accent text and white-on-accent shapes use a darker accent (>= 4.5:1 on every fill of the deck).
ACC_D = "0062AD"
F_REG, F_MED, F_SEMI = "Inter", "Inter Medium", "Inter SemiBold"

ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
ANCHOR = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}


import re
NB = "\u00a0"


def typo(s):
    """Russian typography: glue numbers to units, short prepositions to the next word."""
    s = s.replace("р. д.", "р." + NB + "д.").replace("п. п.", "п." + NB + "п.")
    s = s.replace("Банк России", "Банк" + NB + "России").replace("Банком России", "Банком" + NB + "России")
    s = s.replace("млн ₽", "млн" + NB + "₽").replace("тыс. ₽", "тыс." + NB + "₽").replace("млрд ₽", "млрд" + NB + "₽")
    s = re.sub(r"(?<=\d) (?=(тыс|млн|млрд|%|₽|р\.|мес|нед|ч\b|с\b|дн|год|лет|из\b|п\.))", NB, s)
    s = re.sub(r"(?<=\bиз) (?=\d)", NB, s)
    s = re.sub(r"(№|пп\.|чч\.|ст\.|п\.|с\.|ч\.) (?=\d)", lambda m: m.group(1) + NB, s)
    s = re.sub(r"(?<![\w-])([вксуоиаВКСУОИА]) ", lambda m: m.group(1) + NB, s)
    s = re.sub(r"(?<=\b[IV]) (?=(кв\.|пол\.))", NB, s)
    return s


def rgb(h):
    return RGBColor.from_string(h)


def R(text, **o):
    return (text, o)


def P(content, **style):
    """A paragraph: content is a str or a list of R(...) runs; style: size, font, color, align, after, before, bullet, line."""
    runs = [R(content)] if isinstance(content, str) else content
    return {"runs": runs, **style}


def _set_typeface(run, name):
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
        el = rPr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rPr, qn(tag))
        el.set("typeface", name)


def _bullet(p, indent_in=0.15, char="•", color=ACC):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(indent_in))))
    pPr.set("indent", str(-int(Inches(indent_in))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont", "a:buClr"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    buClr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(buClr, qn("a:srgbClr")).set("val", color)
    etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
    etree.SubElement(pPr, qn("a:buChar")).set("char", char)


def fill_tf(tf, paras, base=None):
    base = base or {}
    for i, para in enumerate(paras):
        st = {**base, **{k: v for k, v in para.items() if k != "runs"}}
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = ALIGN[st.get("align", "l")]
        if st.get("after") is not None:
            p.space_after = Pt(st["after"])
        if st.get("before") is not None:
            p.space_before = Pt(st["before"])
        if st.get("line"):
            p.line_spacing = st["line"]
        if st.get("bullet"):
            _bullet(p, st.get("indent", 0.15), color=st.get("bucolor", ACC))
        for text, ro in para["runs"]:
            o = {**st, **ro}
            r = p.add_run()
            r.text = typo(text)
            r.font.size = Pt(o.get("size", 11))
            col = o.get("color", TXT)
            if col == ACC and o.get("size", 11) < 14:
                col = ACC_D
            r.font.color.rgb = rgb(col)
            _set_typeface(r, o.get("font", F_REG))
    return tf


def _frame(tf, margin, anchor, wrap=True):
    l, t, r, b = margin
    tf.word_wrap = wrap
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = (Inches(l), Inches(t), Inches(r), Inches(b))
    tf.vertical_anchor = ANCHOR[anchor]


def tbox(slide, x, y, w, h, paras, anchor="t", margin=(0, 0, 0, 0), name=None, base=None):
    sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        sh.name = name
    _frame(sh.text_frame, margin, anchor)
    fill_tf(sh.text_frame, paras, base)
    return sh


def _strip_style(sh):
    st = sh._element.find(qn("p:style"))
    if st is not None:
        sh._element.remove(st)


def card(slide, x, y, w, h, fill=CARD, radius=0.07, paras=None, anchor="t", pad=0.15, name=None,
         line=None, dash=False, base=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    sh = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    _strip_style(sh)
    if name:
        sh.name = name
    if radius:
        # adj is relative to the shorter side
        sh.adjustments[0] = min(0.5, radius / min(w, h))
    if fill:
        sh.fill.solid()
        sh.fill.fore_color.rgb = rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = rgb(line)
        sh.line.width = Pt(1)
        if dash:
            from pptx.enum.dml import MSO_LINE_DASH_STYLE
            sh.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    else:
        sh.line.fill.background()
    pads = pad if isinstance(pad, tuple) else (pad, pad, pad, pad)
    _frame(sh.text_frame, pads, anchor)
    if paras:
        fill_tf(sh.text_frame, paras, base)
    else:
        sh.text_frame.paragraphs[0].text = ""
    return sh


def badge_width(text, size=9, font=F_MED):
    from metrics import width_pt
    return width_pt(text, size, font)[0] / 72 + 0.24


def badge(slide, x, y, text, kind="blue", size=9, h=0.24, w=None):
    fill, color = {"blue": (BLUE, ACC), "grey": ("E6E6E6", TXT), "white": (WHITE, ACC),
                   "solid": (ACC, WHITE)}[kind]
    w = w or badge_width(text, size)
    sh = card(slide, x, y, w, h, fill=fill, radius=h / 2, pad=(0.05, 0, 0.05, 0), anchor="m",
              paras=[P([R(text)], size=size, font=F_MED, color=color, align="c")], name=f"Badge: {text}")
    sh.text_frame.word_wrap = False
    return sh


def circle_num(slide, x, y, n, d=0.28, fill=ACC_D, color=WHITE, size=10):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    _strip_style(sh)
    sh.name = f"Step {n}"
    sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
    sh.line.fill.background()
    _frame(sh.text_frame, (0, 0, 0, 0), "m", wrap=False)
    fill_tf(sh.text_frame, [P(str(n), size=size, font=F_SEMI, color=color, align="c")])
    return sh


def logo(slide, x=7.72, y=0.33):
    if hasattr(LOGO, "seek"):
        LOGO.seek(0)
    pic = slide.shapes.add_picture(LOGO, Inches(x), Inches(y), Inches(1.95), Inches(0.24))
    pic.name = "Логотипы ВТБ и Финансового университета"
    pic._element.nvPicPr.cNvPr.set("descr", "Логотипы ВТБ (титульный спонсор) и Финансового университета")
    return pic


def title(slide, text, w=7.25, x=0.24, y=0.25, size=26):
    """Slide title; '|' marks a manual line break."""
    sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(1.12))
    sh.name = "Заголовок"
    _frame(sh.text_frame, (0.1, 0.1, 0.1, 0.05), "t")
    p = sh.text_frame.paragraphs[0]
    for i, part in enumerate(text.split("|")):
        if i:
            p.add_line_break()
        r = p.add_run()
        r.text = typo(part)
        r.font.size = Pt(size)
        r.font.color.rgb = rgb(TXT)
        _set_typeface(r, F_SEMI)
    return sh


def footnote(slide, text, x=0.25, y=5.02, w=8.95, h=0.5, color=MUTED, size=7.5):
    return tbox(slide, x, y, w, h, [P(text, size=size, color=color, line=1.0)], anchor="b",
                name="Источники")


def page_no(slide, n, x=9.3, y=5.23, color=TXT):
    return tbox(slide, x, y, 0.37, 0.25, [P(str(n), size=8, color=color, align="r")], anchor="b",
                name="Номер слайда")


def clear_placeholders(slide):
    for sh in list(slide.placeholders):
        sh._element.getparent().remove(sh._element)


def no_fill_chart(chart):
    """Transparent chart area and plot area."""
    cs = chart._chartSpace
    for parent in (cs, cs.find(qn("c:chart")).find(qn("c:plotArea"))):
        sp = parent.find(qn("c:spPr"))
        if sp is None:
            sp = etree.SubElement(parent, qn("c:spPr"))
            # c:spPr must precede c:txPr / externalData etc. in chartSpace; move into place
            if parent is cs:
                txPr = cs.find(qn("c:txPr"))
                anchor = txPr if txPr is not None else cs.find(qn("c:externalData"))
                if anchor is not None:
                    anchor.addprevious(sp)
        for ch in list(sp):
            sp.remove(ch)
        etree.SubElement(sp, qn("a:noFill"))
        ln = etree.SubElement(sp, qn("a:ln"))
        etree.SubElement(ln, qn("a:noFill"))
