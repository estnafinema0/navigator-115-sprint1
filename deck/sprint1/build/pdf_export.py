"""pptx -> PDF via the local R7-Office converter (x2t), then PNG previews.

Inter is embedded in the template, but x2t does not read embedded fonts and Inter is not installed here,
so the PDF copy maps Inter to Arial (embeddable, Cyrillic): Arial is 0.94 of Inter width, Arial Bold 0.99
of Inter SemiBold, so text that fits in Inter fits in the PDF too. Inter Medium and SemiBold become Arial Bold.
The .pptx itself keeps Inter. (Open Sans and Liberation from R7/user fonts render broken glyphs in x2t: not used.)
usage: python pdf_export.py IN.pptx OUT.pdf [PNG_DIR [GRID.png]]
"""
import os, re, subprocess, sys, tempfile, zipfile
src, out_pdf = sys.argv[1], os.path.abspath(sys.argv[2])
png_dir = sys.argv[3] if len(sys.argv) > 3 else None
grid = sys.argv[4] if len(sys.argv) > 4 else None
here = os.path.dirname(os.path.abspath(__file__))
MAP = {"Inter SemiBold": "Arial", "Inter Medium": "Arial", "Inter Light": "Arial", "Inter": "Arial"}
BOLD = re.compile(r'(<a:rPr[^>]*?)(/?>)(?=(?:(?!</a:rPr>).)*?typeface="Inter (?:SemiBold|Medium)")')
tmp = tempfile.mkdtemp(prefix="deckpdf-")
mapped = os.path.join(tmp, "mapped.pptx")
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(mapped, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xml"):
            s = data.decode("utf-8")
            s = BOLD.sub(lambda m: m.group(1) + ("" if ' b="1"' in m.group(1) else ' b="1"') + m.group(2), s)
            for k in sorted(MAP, key=len, reverse=True):
                s = s.replace(f'typeface="{k}"', f'typeface="{MAP[k]}"')
            if item.filename == "ppt/presentation.xml":
                s = re.sub(r"<p:embeddedFontLst>.*?</p:embeddedFontLst>", "", s, flags=re.S)
            data = s.encode("utf-8")
        zout.writestr(item, data)
subprocess.run([os.path.join(here, "x2t_params.sh"), mapped, out_pdf], check=True)
print("pdf:", out_pdf)
if png_dir:
    os.makedirs(png_dir, exist_ok=True)
    args = [sys.executable, os.path.join(here, "render.py"), out_pdf, os.path.join(png_dir, "s"), "2.0"]
    if grid:
        args.append(grid)
    subprocess.run(args, check=True)
