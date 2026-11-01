import sys, os, pypdfium2 as pdfium
from PIL import Image
pdf, prefix = sys.argv[1], sys.argv[2]
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
doc = pdfium.PdfDocument(pdf)
paths = []
for i in range(len(doc)):
    img = doc[i].render(scale=scale).to_pil()
    p = f"{prefix}-{i+1:02d}.png"; img.save(p); paths.append(p)
print("\n".join(os.path.abspath(p) for p in paths))
# grid
if len(sys.argv) > 4:
    thumbs = [Image.open(p) for p in paths]
    w, h = thumbs[0].size; tw, th = w//2, h//2; cols = 4; rows = (len(thumbs)+cols-1)//cols
    grid = Image.new("RGB", (cols*tw, rows*th), "white")
    for k, t in enumerate(thumbs):
        grid.paste(t.resize((tw, th)), ((k%cols)*tw, (k//cols)*th))
    grid.save(sys.argv[4]); print(os.path.abspath(sys.argv[4]))
