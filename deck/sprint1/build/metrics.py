"""Inter advance-width metrics from fontsource WOFF subsets (merged cmaps)."""
import glob, os
from fontTools.ttLib import TTFont
HERE = os.path.dirname(os.path.abspath(__file__))
_cache = {}
WEIGHT = {"Inter": 400, "Inter Medium": 500, "Inter SemiBold": 600, "Inter Light": 300}
def _load(weight):
    if weight in _cache: return _cache[weight]
    adv = {}; upem = None
    for f in sorted(glob.glob(f"{os.environ.get('INTER_DIR', HERE + '/inter')}/package/files/inter-*-{weight}-normal.woff")):
        t = TTFont(f); upem = t["head"].unitsPerEm
        hm = t["hmtx"].metrics
        for cp, g in t.getBestCmap().items():
            adv.setdefault(cp, hm[g][0])
    if not adv:
        raise SystemExit('Inter metrics not found: put @fontsource/inter 5.1.0 into ./inter/package or set INTER_DIR')
    _cache[weight] = (adv, upem)
    return _cache[weight]
def width_pt(text, size_pt, family="Inter", bold=False):
    w = WEIGHT.get(family, 400)
    if bold and w < 600: w = 700 if w >= 500 else 600
    adv, upem = _load(w)
    missing = [c for c in text if ord(c) not in adv and c not in "\n"]
    tot = sum(adv.get(ord(c), 0.6 * upem) for c in text)
    return tot * size_pt / upem, missing
LINE = 1.2109  # (ascender 0.96875 + descender 0.2421875) em
