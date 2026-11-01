"""Замер стража M9 (make guard-eval): синтетика dev/test и отложенный набор жюри и красной команды.

dev — для настройки правил; test — замер (после правок 21.10 уже не отложенный, см. reports/guard-2026-10-21.md).
holdout-2026-10-27 — фразы члена жюри и красной команды от 27.10 (не реальные тексты банков). Правила 27.10
правились по этим фразам, поэтому после правок набор тоже не отложенный: в отчёте «до» и «после».
«До» считается кодом стража из коммита BASELINE (до правок 27.10), «после» — текущим кодом.
Пороги (PROMPT.md, разд. 9): запрещённое — recall ≥0,95, precision ≥0,8.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from navigator.guard import check  # noqa: E402

BASELINE = "8e8dba8"  # последний коммит до правок стража 27.10
EXPECT = {"E1": "yes", "E2": "norm", "E3": "present", "E4": "yes", "deadline": "yes", "E5": "external", "E6": "yes"}
SETS = [("dev", "notices-dev.jsonl"), ("test", "notices-test.jsonl"), ("holdout-2026-10-27", "notices-holdout-2026-10-27.jsonl")]


def baseline_check(ref: str):
    """Функция check стража из git-коммита ref (для честного «до»)."""
    src = subprocess.run(["git", "show", f"{ref}:api/navigator/guard.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    mod = types.ModuleType("guard_baseline")
    sys.modules["guard_baseline"] = mod
    exec(compile(src, f"guard@{ref}", "exec"), mod.__dict__)
    return mod.check


def measure(recs: list[dict], chk=check) -> dict:
    tp = fp = fn = 0
    cat: dict[str, list[int]] = {}
    el = {e: [0, 0] for e in EXPECT}
    misses, false_red = [], []
    for r in recs:
        g = chk(r["text"])
        found = {f["id"] for f in g.forbidden}
        gold = set(r["forbidden"])
        for c in gold | found:
            s = cat.setdefault(c, [0, 0, 0])  # tp, fp, fn
            s[0] += c in gold and c in found
            s[1] += c in found and c not in gold
            s[2] += c in gold and c not in found
        tp += len(gold & found)
        fp += len(found - gold)
        fn += len(gold - found)
        if gold - found:
            misses.append(r["id"])
        if found - gold:
            false_red.append(r["id"])
        for e, want in EXPECT.items():
            if e not in r.get("elements", {}):  # в отложенном наборе размечены не все элементы
                continue
            exp = want if r["elements"][e] else "no"
            got = g.elements[e]
            ok = got == exp or (e == "E6" and exp == "no" and got == "partial")
            el[e][0] += ok
            el[e][1] += 1
    rec = tp / (tp + fn) if tp + fn else None
    prec = tp / (tp + fp) if tp + fp else None
    return {"recall": rec, "precision": prec, "tp": tp, "fp": fp, "fn": fn, "cat": cat, "el": el, "n": len(recs),
            "misses": misses, "false_red": false_red}


def fmt(x):
    return "н/д" if x is None else f"{x:.2f}"


def block(title: str, m: dict) -> list[str]:
    lines = [f"### {title} (n={m['n']})", "",
             f"Запрещённое: recall **{fmt(m['recall'])}**, precision **{fmt(m['precision'])}** (tp={m['tp']}, fp={m['fp']}, fn={m['fn']}).", "",
             "| Категория | tp | fp | fn |", "|---|---|---|---|"]
    for c, (a, b, d) in sorted(m["cat"].items()):
        lines.append(f"| {c} | {a} | {b} | {d} |")
    els = [(e, ok, n) for e, (ok, n) in m["el"].items() if n]
    if els:
        lines += ["", "| Элемент | Точность |", "|---|---|"]
        lines += [f"| {e} | {ok}/{n} = {ok / n:.2f} |" for e, ok, n in els]
    if m["misses"] or m["false_red"]:
        lines += ["", f"Пропуски: {', '.join(m['misses']) or 'нет'}. Ложный красный: {', '.join(m['false_red']) or 'нет'}."]
    return lines + [""]


def corpus_line(old) -> str:
    """Сколько реальных текстов корпуса сменили вердикт (локально, тексты никуда не отправляются; разметки запрещённого нет)."""
    path = ROOT / "data/real/corpus.jsonl"
    if not path.exists():
        return "- Корпус реальных текстов недоступен: сравнение «до/после» на нём не сделано."
    recs = [json.loads(x) for x in path.read_text().splitlines() if x]
    changed = []
    for r in recs:
        a, b = old(r["text"]), check(r["text"])
        fa, fb = sorted(f["id"] for f in a.forbidden), sorted(f["id"] for f in b.forbidden)
        if fa != fb or a.light != b.light or b.review:
            changed.append(f"{r['id']} ({a.light} → {b.light}{'; ' + ', '.join(x['id'] for x in b.review) if b.review else ''})")
    return (f"- На {len(recs)} реальных текстах корпуса (`data/real/`, разметки запрещённого нет) правки изменили вердикт или пометку review в "
            f"{len(changed)}: {'; '.join(changed) or 'нет'}.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=BASELINE, help="git-коммит стража для столбца «до»")
    args = ap.parse_args()
    old = baseline_check(args.baseline)
    data = {name: [json.loads(x) for x in (ROOT / "eval/guard" / fn).read_text().splitlines() if x] for name, fn in SETS}
    lines = [f"# Страж M9: синтетика и отложенный набор 27.10, {date.today():%d.%m.%Y}", "",
             "Сформирован `eval/run_guard.py`. Все тексты: синтетика, реальных текстов банков здесь нет.", "",
             "- `dev`, `test`: синтетика `scripts/guard_set.py`; test перестал быть отложенным 21.10 (`reports/guard-2026-10-21.md`).",
             "- `holdout-2026-10-27`: отложенный набор, авторы: жюри-агент (J01–J10, `jury/sprint1/score-risk-compliance.md`) и "
             "красная команда-агент (R01–R15, `jury/sprint1/redteam.md`), 27.10, не реальные тексты банков. Каждая фраза "
             "дописана к полному синтетическому уведомлению.",
             "",
             f"«До»: код стража из коммита `{args.baseline}`, «после»: текущий. Пороги: recall запрещённого ≥0,95, precision ≥0,8.", ""]
    res = {name: (measure(recs, old), measure(recs)) for name, recs in data.items()}
    hb, ha = res["holdout-2026-10-27"]
    n_legit = sum(not r["forbidden"] for r in data["holdout-2026-10-27"])
    relabeled = sum("relabel" in r for name in ("dev", "test") for r in data[name])
    lines += ["## Главное, честно", "",
              f"- На отложенном наборе 27.10 до правок страж ловил {hb['tp']} из {hb['tp'] + hb['fn']} запрещённых формулировок "
              f"(recall **{fmt(hb['recall'])}**) и давал ложный красный на {len(hb['false_red'])} законных текстах из {n_legit} "
              f"(precision **{fmt(hb['precision'])}**). Это ниже порогов.",
              f"- После правок на том же наборе recall **{fmt(ha['recall'])}**, precision **{fmt(ha['precision'])}**. "
              "Правила дописаны по этим же фразам, поэтому **набор больше не отложенный**: цифры «после» показывают, что "
              "пропуски закрыты, а не обобщение. Для банка они не доказательство.",
              f"- Precision на наборе посчитана всего на {n_legit} законных фразах и на полных уведомлениях без фраз; ложные "
              "срабатывания на реальных текстах банков не размечены (не измерено).",
              "- В протоколе красной команды из 17 формулировок дословно приведены 13; 4 не приведены и в набор не вошли. "
              "Из 9 формулировок жюри дословно приведены 7, 2 (J08, J09) реконструированы по правкам из протокола.",
              f"- Разметка E3 в dev/test изменена в {relabeled} записях: при отказе назвать причину E3 = «нет» "
              "(правило из протокола жюри). Поэтому E3 «до» в dev/test ниже, чем в отчёте 21.10.",
              corpus_line(old),
              "- Новый отложенный замер нужен на реальных уведомлениях банков, размеченных ПОД/ФТ (порог recall ≥0,95): не проведён.",
              "- Жёлтый «нужна позиция комплаенса» (поле `review`: РФМ или суд как основание приостановления, ссылка на 375-П) "
              "проверен только юнит-тестами (`tests/test_guard.py`), в наборе не измерялся.", ""]
    for name in data:
        before, after = res[name]
        lines += [f"## {name}", ""]
        lines += block(f"до правок 27.10 ({args.baseline})", before)
        lines += block("после правок 27.10", after)
    out = ROOT / "reports" / f"guard-{date.today():%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
