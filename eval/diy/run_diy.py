"""Эксперимент «против DIY-ChatGPT» (PROMPT.md, разд. 9).

20 дословных реальных текстов → (а) промпт №1 из гайда Клерка на той же локальной модели,
без схемы и валидатора; (б) наш конвейер: правила + LLM (slim) + combine + валидатор.
Метрики только детерминированные (регулярные выражения и поиск цитат), LLM-as-judge не используется.

Запуск:
    .venv/bin/python eval/diy/run_diy.py            # метрики по сохранённым ответам; недостающие ответы догенерируются
    .venv/bin/python eval/diy/run_diy.py --rerun    # заново вызвать модель для всех 20 текстов (обе стороны)
    .venv/bin/python eval/diy/run_diy.py --generate-only

Реальные тексты уходят только в локальную модель (Ollama на localhost).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from navigator.evidence import check_span, locate, nfc  # noqa: E402

DIY_DIR = ROOT / "eval" / "diy"
OUT_DIR = DIY_DIR / "outputs"
OURS_DIR = DIY_DIR / "ours"
PROMPT_FILE = DIY_DIR / "klerk_prompt1.local.txt"
PLACEHOLDER = "[вставьте обезличенный текст]"
CORPUS = ROOT / "data" / "real" / "corpus.jsonl"
CACHE = ROOT / "eval" / "cache"
N_TEXTS = 20

OLLAMA_URL = "http://localhost:11434"
MODEL = "hf.co/t-tech/T-lite-it-2.1-GGUF:Q4_K_M"
# Как в navigator.llm.extract (temperature 0, seed 42, num_ctx 8192), но без format/схемы и без системного промпта.
# num_predict — только предохранитель от зацикливания; обрезанный ответ помечается done_reason=length.
DIY_OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 3000}


# ---------------------------------------------------------------- данные

def load_items() -> list[dict]:
    """Первые 20 текстов с text_type == verbatim в порядке файла corpus.jsonl."""
    rows = [json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [{"id": r["id"], "bank": r.get("bank"), "text": r["text"]} for r in rows if r["text_type"] == "verbatim"][:N_TEXTS]


def load_prompt() -> str:
    if not PROMPT_FILE.exists():
        raise SystemExit(f"нет {PROMPT_FILE.relative_to(ROOT)}: промпт хранится локально, см. eval/diy/README.md")
    p = PROMPT_FILE.read_text(encoding="utf-8")
    if PLACEHOLDER not in p:
        raise SystemExit("в промпте нет плейсхолдера " + PLACEHOLDER)
    return p


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- генерация: DIY

def diy_generate(item: dict, prompt: str, force: bool) -> None:
    path = OUT_DIR / f"{item['id']}.md"
    if path.exists() and not force:
        return
    import httpx
    user = prompt.replace(PLACEHOLDER, item["text"])
    payload = {"model": MODEL, "messages": [{"role": "user", "content": user}], "stream": False, "think": False,
               "options": DIY_OPTIONS}
    t0 = time.time()
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=900)
    r.raise_for_status()
    data = r.json()
    secs = round(time.time() - t0, 2)
    meta = {"id": item["id"], "model": MODEL, "options": DIY_OPTIONS, "think": False, "format": None,
            "seconds": secs, "eval_count": data.get("eval_count"), "prompt_eval_count": data.get("prompt_eval_count"),
            "done_reason": data.get("done_reason"), "prompt_sha256": sha(prompt), "text_sha256": sha(item["text"]),
            "generated_at": datetime.now().isoformat(timespec="seconds")}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("<!-- diy-meta " + json.dumps(meta, ensure_ascii=False) + " -->\n\n"
                    + data["message"]["content"].strip() + "\n", encoding="utf-8")
    print(f"DIY {item['id']}: {secs} с, {data.get('eval_count')} ток., {data.get('done_reason')}", flush=True)


def diy_read(item_id: str) -> tuple[dict, str]:
    raw = (OUT_DIR / f"{item_id}.md").read_text(encoding="utf-8")
    m = re.match(r"<!-- diy-meta (\{.*?\}) -->\n\n", raw, flags=re.S)
    return json.loads(m.group(1)), raw[m.end():]


# ---------------------------------------------------------------- генерация: наш конвейер

def cache_key(text: str) -> str:
    from navigator.llm import DEFAULT_MODEL
    return hashlib.sha256((DEFAULT_MODEL + "|slim\n" + text).encode()).hexdigest()[:24]


LLM_TIMEOUT = 1200.0  # у navigator.llm.extract по умолчанию 300 с; декодирование по схеме на ноутбуке бывает дольше


def ours_generate(item: dict, force: bool, retry_errors: bool = False) -> None:
    """rules.extract + llm.extract(slim) + combine + validate. Сырой ответ LLM хранится в ours/<ID>.json,
    чтобы пересчёт шёл без модели; eval/cache/ только читается."""
    from navigator import llm as L
    from navigator.rules import extract as rules_extract
    from navigator.validator import validate

    path = OURS_DIR / f"{item['id']}.json"
    text = item["text"]
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if prev and not force and not (retry_errors and "error" in prev["llm_meta"]):
        llm_raw, llm_meta, src = prev["llm_raw"], prev["llm_meta"], prev["llm_source"]
    else:
        cp = CACHE / f"{cache_key(text)}.json"
        if cp.exists() and not force:
            rec = json.loads(cp.read_text(encoding="utf-8"))
            llm_raw, llm_meta, src = rec["raw"], rec["meta"], f"eval/cache/{cp.name}"
        else:
            try:
                llm_raw, llm_meta = L.extract(text, slim=True, timeout=LLM_TIMEOUT)
            except Exception as e:  # как в eval/run_eval.py: невалидный ответ модели считаем пустым
                from navigator.rules import empty
                llm_raw, llm_meta = empty(), {"error": repr(e)[:300]}
            src = "new call (run_diy.py)"
            print(f"OURS {item['id']}: {llm_meta.get('seconds')} с", flush=True)
    rules = rules_extract(text)
    combined = L.combine(rules, llm_raw, text)
    final, rep = validate(combined, text)
    rec = {"id": item["id"], "text_sha256": sha(text), "cache_key": cache_key(text), "llm_source": src,
           "llm_meta": llm_meta, "llm_raw": llm_raw, "final": final, "validation": rep.to_dict()}
    OURS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- main (метрики — ниже, в части 2)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true", help="заново вызвать модель для всех текстов")
    ap.add_argument("--generate-only", action="store_true")
    ap.add_argument("--side", choices=["both", "diy", "ours"], default="both")
    ap.add_argument("--retry-errors", action="store_true", help="наш конвейер: повторить вызовы LLM, которые упали (таймаут)")
    args = ap.parse_args()
    items = load_items()
    prompt = load_prompt()
    if args.side in ("both", "diy"):
        for it in items:
            diy_generate(it, prompt, args.rerun)
    if args.side in ("both", "ours"):
        for it in items:
            ours_generate(it, args.rerun, args.retry_errors)
    if args.generate_only:
        return 0
    return report(items)


# ================================================================ МЕТРИКИ
# Всё ниже — детерминированные правила. Описание и обоснование — eval/diy/README.md.

FX = re.IGNORECASE | re.UNICODE

# ---------- 1. Утверждения DIY и их опора

def _clean_md(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s, flags=FX)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


SELF_RX = re.compile(r"(?<!\w)(я|мне|меня|давайте|разбер[её]м|посмотрим|начн[её]м|рассмотрим|проанализирую|разделю|"
                     r"прочитаю|подготовлю|составлю|перейд[её]м|оформлю|хм|подожд\w*)(?!\w)", FX)
LIST_RX = re.compile(r"^\s*(?:[-*•+]|\d{1,2}[.)])\s+")
SEP_RX = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
ADVICE_COL_RX = re.compile(r"дополнительн|у кого|внутри компании|ответственн", FX)
NUMCELL_RX = re.compile(r"^(№\s*)?\d{1,2}[.)]?$|^№$")


def split_sentences(par: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«\"(])", par) if x.strip()]


def is_heading(line: str) -> bool:
    raw = line.strip()
    if raw.startswith("#") or re.fullmatch(r"-{3,}|\*{3,}|_{3,}", raw):
        return True
    if raw.endswith(":"):  # подводка к таблице / списку
        return True
    if re.fullmatch(r"\*\*[^*]+\*\*:?", raw) and not raw.rstrip(":").rstrip("*").endswith("."):
        return True  # строка целиком жирным без точки — подзаголовок
    return False


def parse_claims(resp: str) -> tuple[list[dict], list[dict]]:
    """Ответ DIY → (утверждения, ячейки таблиц).
    Утверждение = строка данных таблицы | пункт списка | предложение прозы.
    Ячейка таблицы = «поле» (для сравнения с полями нашего конвейера)."""
    claims, cells = [], []
    lines = resp.splitlines()
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if not st:
            i += 1
            continue
        if st.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            header = [_clean_md(c) for c in block[0].strip("|").split("|")]
            for row in block[1:]:
                if SEP_RX.match(row):
                    continue
                cs = [_clean_md(c) for c in row.strip("|").split("|")]
                row_text = " ".join(c for c in cs if c)
                claims.append({"kind": "table_row", "text": row_text})
                for ci, c in enumerate(cs):
                    hname = header[ci] if ci < len(header) else ""
                    cells.append({"kind": "cell", "col": hname, "advice": bool(ADVICE_COL_RX.search(hname)), "text": c})
            continue
        i += 1
        if is_heading(st):
            continue
        m = LIST_RX.match(st)
        if m:
            claims.append({"kind": "list_item", "text": _clean_md(st[m.end():])})
            continue
        for sent in split_sentences(_clean_md(st)):
            if sent.endswith(":"):
                continue
            claims.append({"kind": "sentence", "text": sent})
    return claims, cells


FILLER_EXACT = {"не", "нет", "в", "во", "у", "о", "об", "и", "или", "по", "для", "на", "из", "так", "как", "n", "a",
                "это", "этом", "быть", "может", "можно", "нужно", "надо", "также", "явно", "прямо", "его", "ее", "её",
                "был", "было", "была", "были", "к", "с", "со", "же", "ли", "но", "а", "однако", "ни", "которые",
                "который", "которая", "которых", "этот", "эта", "эти", "здесь", "тут", "там"}
FILLER_STEMS = ("указ", "текст", "запрос", "упомин", "упомян", "отсутств", "уточн", "банк", "требу", "необходим",
                "следует", "данн", "информац", "сведен", "конкретн", "определ", "применим", "письм", "сообщени",
                "уведомлен", "срок", "период", "операци", "документ", "крайн", "дополнительн", "момент", "четк",
                "чётк", "ясн", "однозначн", "неоднозначн", "формулировк", "приведен", "содерж", "предостав", "конкретн",
                "требовани", "пункт", "детал")


def is_absence(text: str) -> bool:
    """«Не указано», «—», «уточнить у банка» — не фактическое утверждение о тексте."""
    t = text.strip()
    if re.match(r"^[^:]{1,60}:\s", t):  # «Крайний срок: не указан» → оцениваем значение после метки
        t = t.split(":", 1)[1]
    toks = re.findall(r"[а-яёa-z0-9]+", t.lower())
    if not toks:
        return True
    if not all(x in FILLER_EXACT or x.startswith(FILLER_STEMS) for x in toks):
        return False
    return any(x in ("не", "нет") or x.startswith(("отсутств", "уточн")) for x in toks)


# «Не указано, когда / какие …» — утверждение об отсутствии, без домысла после «но»
ABSENT_Q_RX = re.compile(r"не\s+(?:указ\w*|уточн\w*|упомина\w*|упомян\w*|сказано|говорится|определ\w*|раскрыва\w*)\s*,?\s*"
                         r"(?:когда|какие|какой|какая|каких|каким|что|где|кто|как|почему|сколько|за\s+какой|в\s+какой|чем|ли)(?!\w)", FX)
CLARIFY_RX = re.compile(r"уточн\w*\s+(?:\w+\s+){0,3}(?:у\s+банка|в\s+банке)|уточнить\s+эти\s+моменты|запросить\s+уточнени\w*", FX)
BUT_RX = re.compile(r"(?<!\w)(?:но|однако|вероятно|возможно|скорее\s+всего|предположительно)(?!\w)", FX)
ADVICE_RX = re.compile(r"дополнительн\w*\s+(?:\w+\s+){0,2}документ|внутри\s+компании|у\s+кого|"
                       r"(?:запросить|получить)\s+(?:\w+\s+){0,2}у\s+(?:отдел|бухгалтер|директор|руководител|юрист|сотрудник)|"
                       r"у\s+(?:отдела|бухгалтер\w*|директора|руководител\w*|финансов\w+\s+отдела)", FX)


def is_claim(c: dict) -> bool:
    t = c["text"]
    if is_absence(t) or NUMCELL_RX.match(t.strip()):
        return False
    if c.get("kind") != "cell" and len(TOK_RX.findall(t)) < 3 and not re.search(r"\d", t):
        return False  # обрывок («Поэтому» в конце обрезанного ответа)
    if c.get("kind") == "sentence" and SELF_RX.search(t):
        return False  # речь модели о себе («Давайте разберём…», «Теперь я разделю…»)
    if c.get("kind") != "cell" and not BUT_RX.search(t) and (ABSENT_Q_RX.search(t) or CLARIFY_RX.search(t)):
        return False  # «Не указано, когда…», «стоит уточнить у банка» — то, что промпт и просит отмечать
    return True


def is_advice(c: dict) -> bool:
    """Ответ на «советные» вопросы промпта: какие документы могут дополнительно подтвердить, у кого внутри компании спросить."""
    return c["advice"] if c.get("kind") == "cell" else bool(ADVICE_RX.search(c["text"]))


PUNCT_EDGE = " \t.,;:!?«»\"'()[]—–-…*"


def support_locate(claim: str, text: str, n: int = 4) -> str | None:
    """Строгая проверка: есть ли в утверждении окно из n подряд слов, которое navigator.evidence.locate
    находит в тексте банка (без учёта регистра; locate терпим к пробелам, ё/е, кавычкам и тире).
    Утверждение короче n слов — опора, если оно целиком найдено в тексте."""
    src = text.lower()
    ws = [w for w in claim.split() if w.strip(PUNCT_EDGE)]
    if not ws:
        return None
    if len(ws) < n:
        q = " ".join(ws).strip(PUNCT_EDGE).lower()
        return q if q and locate(src, q) else None
    for k in range(len(ws) - n + 1):
        q = " ".join(ws[k:k + n]).strip(PUNCT_EDGE).lower()
        if len(q.split()) >= n and locate(src, q):
            return q
    return None


TOK_RX = re.compile(r"\w+(?:[.,\-/]\w+)*", FX)


def _toks(s: str) -> list[str]:
    return [t for t in TOK_RX.findall(nfc(s).lower().replace("ё", "е"))]


def support_tokens(claim: str, text: str, n: int = 4) -> bool:
    """Мягкая проверка (чувствительность): 4 подряд слова без учёта пунктуации между ними."""
    ct, st = _toks(claim), _toks(text)
    if not ct:
        return False
    k = min(n, len(ct))
    grams = {tuple(st[i:i + k]) for i in range(len(st) - k + 1)}
    return any(tuple(ct[i:i + k]) in grams for i in range(len(ct) - k + 1))


# ---------- 2. Факты: нормы, законы, даты, сроки, суммы, органы

ATOM_RX = re.compile(r"(?<![\w.])(?:(?P<abbr>пп|п|ч|ст)\.\s*|(?P<word>подпункт|пункт|част|стать)[а-яё]*\s+)"
                     r"(?P<num>\d+(?:\.\d+)*)", FX)
ATOM_MORE_RX = re.compile(r"(?:\s*,\s*|\s+и\s+)(\d+\.\d+(?:\.\d+)*)")
ATOM_TYPE = {"пп": "пп", "подпункт": "пп", "п": "п", "пункт": "п", "ч": "ч", "част": "ч", "ст": "ст", "стать": "ст"}
CLUSTER_GAP_RX = re.compile(r"^[\s.,;]*(?:(?:и|или)\s+)?$", FX)
LAW_RX = [("115-ФЗ", re.compile(r"(?<!\d)115\s*[-‑–—]?\s*ФЗ|О\s+противодействии\s+легализации", FX)),
          ("161-ФЗ", re.compile(r"(?<!\d)161\s*[-‑–—]?\s*ФЗ|О\s+национальной\s+платежной\s+системе", FX))]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
DATE_NUM_RX = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
DATE_TXT_RX = re.compile(r"(?<!\d)(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", FX)
NUMWORDS = {"одного": 1, "один": 1, "двух": 2, "два": 2, "трех": 3, "трёх": 3, "три": 3, "четырех": 4, "четырёх": 4,
            "четыре": 4, "пяти": 5, "пять": 5, "шести": 6, "шесть": 6, "семи": 7, "семь": 7, "восьми": 8, "восемь": 8,
            "девяти": 9, "десяти": 10, "десять": 10, "пятнадцати": 15, "пятнадцать": 15, "двадцати": 20,
            "двадцать": 20, "тридцати": 30, "тридцать": 30}
DAYS_RX = re.compile(r"(?<![\w.,])(?P<n>\d{1,3}|" + "|".join(NUMWORDS) + r")(?:\s*\([^)]{1,25}\))?\s*"
                     r"(?P<kind>рабоч\w*|календарн\w*|банковск\w*)?\s+(?:дн(?:ей|я)|день|сут(?:ок|ки))(?!\w)", FX)
SUM_RX = re.compile(r"(?<![\d.,])(?P<int>\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](?P<frac>\d{1,2}))?\s*"
                    r"(?P<mult>тыс\.?|тысяч\w*|млн\.?|миллион\w*|млрд\.?|миллиард\w*)?\s*(?:₽|руб\w*\.?|RUB|р\.)", FX)
ORG_RX = {"МВК": re.compile(r"(?<!\w)МВК(?!\w)|межведомственн\w*\s+комисси\w*", FX),
          "ЦБ": re.compile(r"(?<!\w)ЦБ(?!\w)|Банк\w*\s+России|Центральн\w*\s+банк\w*", FX),
          "суд": re.compile(r"(?<!\w)суд(?:а|у|ом|е|ы|ов|ам|ами|ах|ебн\w*)?(?!\w)", FX),
          "Росфинмониторинг": re.compile(r"Росфинмониторинг\w*|(?<!\w)(?:РФМ|ФСФМ)(?!\w)", FX)}


def atoms_with_pos(text: str) -> list[tuple[int, int, str]]:
    out = []
    for m in ATOM_RX.finditer(text):
        t = ATOM_TYPE[(m.group("abbr") or m.group("word")).lower()]
        out.append((m.start(), m.end(), f"{t}:{m.group('num')}"))
        pos = m.end()
        while True:
            mm = ATOM_MORE_RX.match(text, pos)
            if not mm:
                break
            out.append((mm.start(1), mm.end(), f"{t}:{mm.group(1)}"))
            pos = mm.end()
    return out


def norm_clusters(text: str) -> list[dict]:
    """Ссылка на норму = цепочка «п./ч./ст. N» рядом друг с другом. С «ст.» — норма закона;
    без «ст.», но с многоуровневым номером (9.2.24) — пункт договора/правил; иначе (п. 1) — нумерация, не норма."""
    atoms = atoms_with_pos(text)
    groups: list[list[tuple[int, int, str]]] = []
    for a in atoms:
        if groups and CLUSTER_GAP_RX.match(text[groups[-1][-1][1]:a[0]]):
            groups[-1].append(a)
        else:
            groups.append([a])
    out = []
    for g in groups:
        keys = [x[2] for x in g]
        if any(k.startswith("ст:") for k in keys):
            kind = "norm_law"
        elif any("." in k.split(":", 1)[1] for k in keys):
            kind = "norm_contract"
        else:
            continue
        out.append({"kind": kind, "atoms": sorted(set(keys)), "raw": text[g[0][0]:g[-1][1]]})
    return out


def _days_kind(s: str | None) -> str:
    if not s:
        return "unspecified"
    s = s.lower()
    return "calendar" if s.startswith("календарн") else "working"


def _num(s: str) -> int:
    return int(s) if s.isdigit() else NUMWORDS[s.lower()]


def facts_from_text(text: str) -> list[dict]:
    """Все факты проверяемых видов, найденные регулярками в свободном тексте."""
    text = nfc(text)
    out = [{"cat": c["kind"], "key": "|".join(c["atoms"]), "atoms": c["atoms"], "raw": c["raw"]} for c in norm_clusters(text)]
    for law, rx in LAW_RX:
        m = rx.search(text)
        if m:
            out.append({"cat": "law", "key": law, "raw": m.group(0)})
    for m in DATE_NUM_RX.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            out.append({"cat": "date", "key": f"{y:04d}-{mo:02d}-{d:02d}", "raw": m.group(0)})
    for m in DATE_TXT_RX.finditer(text):
        out.append({"cat": "date", "key": f"{int(m.group(3)):04d}-{MONTHS.index(m.group(2).lower()) + 1:02d}-{int(m.group(1)):02d}",
                    "raw": m.group(0)})
    for m in DAYS_RX.finditer(text):
        n, k = _num(m.group("n")), _days_kind(m.group("kind"))
        out.append({"cat": "days", "key": f"{n}:{k}", "n": n, "days_kind": k, "raw": m.group(0)})
    for m in SUM_RX.finditer(text):
        v = float(re.sub(r"\D", "", m.group("int")) + "." + (m.group("frac") or "0"))
        mult = (m.group("mult") or "").lower()
        v *= (1e3 if mult.startswith("тыс") else 1e6 if mult.startswith(("млн", "миллион"))
              else 1e9 if mult.startswith(("млрд", "миллиард")) else 1)
        out.append({"cat": "sum", "key": f"{v:.2f}", "raw": m.group(0)})
    for name, rx in ORG_RX.items():
        m = rx.search(text)
        if m:
            out.append({"cat": "org", "key": name, "raw": m.group(0)})
    return dedup(out)


def dedup(facts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in facts:
        if (f["cat"], f["key"]) not in seen:
            seen.add((f["cat"], f["key"]))
            out.append(f)
    return out


class Source:
    """Что есть в тексте банка (теми же регулярками)."""

    def __init__(self, text: str):
        text = nfc(text)
        self.atoms = {a[2] for a in atoms_with_pos(text)}
        f = facts_from_text(text)
        self.keys = {(x["cat"], x["key"]) for x in f}
        self.days = [(x["n"], x["days_kind"]) for x in f if x["cat"] == "days"]

    def has(self, fact: dict) -> tuple[bool, str]:
        c = fact["cat"]
        if c in ("norm_law", "norm_contract"):
            miss = [a for a in fact["atoms"] if a not in self.atoms]
            return (not miss, "" if not miss else "нет в тексте: " + ", ".join(miss))
        if c == "days":
            same_n = [k for n, k in self.days if n == fact["n"]]
            if not same_n:
                return False, "числа дней нет в тексте"
            if fact["days_kind"] == "unspecified" or fact["days_kind"] in same_n:
                return True, ""
            return False, "добавлен вид дней (" + fact["days_kind"] + "), в тексте: " + "/".join(same_n)
        return ((c, fact["key"]) in self.keys, "")


# ---------- 3. Наш конвейер: поля и факты из структуры

ROUTE_ORG = {"mvk": "МВК", "cbr_complaint": "ЦБ", "cbr_161_exclusion": "ЦБ", "court": "суд"}
UNIT_KIND = {"working_days": "working", "calendar_days": "calendar", "days_unspecified": "unspecified"}


def ours_fields(final: dict) -> list[tuple[str, list[dict]]]:
    """Заполненные поля результата (значение есть) и их цитаты."""
    out = []
    sc = final.get("scenario") or {}
    if sc.get("value") not in (None, "unknown"):
        out.append(("scenario", sc.get("evidence") or []))
    for name in ("measures", "requested_items", "deadlines", "response_channels", "consequences", "operations"):
        for i, it in enumerate(final.get(name) or []):
            out.append((f"{name}[{i}]", it.get("evidence") or []))
            if isinstance(it.get("period"), dict):
                out.append((f"{name}[{i}].period", it["period"].get("evidence") or []))
    for i, it in enumerate((final.get("legal_basis") or {}).get("items") or []):
        out.append((f"legal_basis.items[{i}]", it.get("evidence") or []))
    rs = final.get("reason") or {}
    if rs.get("level") not in (None, "none"):
        out.append(("reason", rs.get("evidence") or []))
    ns = final.get("next_steps") or {}
    if ns.get("stated"):
        out.append(("next_steps", ns.get("evidence") or []))
    if isinstance(final.get("period"), dict):
        out.append(("period", final["period"].get("evidence") or []))
    ap = final.get("appeal") or {}
    for i, r in enumerate(ap.get("routes") or []):
        out.append((f"appeal.routes[{i}]", r.get("evidence") or []))
    if isinstance(ap.get("explicit_denial"), dict):
        out.append(("appeal.explicit_denial", ap["explicit_denial"].get("evidence") or []))
    for k, v in (final.get("request_meta") or {}).items():
        if isinstance(v, dict):
            out.append((f"request_meta.{k}", v.get("evidence") or []))
    return out


def _iso_to_key(d: str | None) -> str | None:
    return d if d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None


def ours_facts(final: dict) -> list[dict]:
    out = []
    for it in (final.get("legal_basis") or {}).get("items") or []:
        if it.get("kind") == "law":
            atoms = [f"{t}:{it[f]}" for t, f in (("пп", "subpoint"), ("п", "point"), ("ч", "part"), ("ст", "article")) if it.get(f)]
            if atoms:
                out.append({"cat": "norm_law", "key": "|".join(sorted(atoms)), "atoms": sorted(atoms), "raw": it.get("canonical")})
            if it.get("law") in ("115-ФЗ", "161-ФЗ"):
                out.append({"cat": "law", "key": it["law"], "raw": it.get("canonical")})
        elif it.get("kind") == "contract" and it.get("contract_clause"):
            nums = re.findall(r"\d+(?:\.\d+)*", it["contract_clause"])
            atoms = sorted({f"п:{n}" for n in nums})
            if atoms:
                out.append({"cat": "norm_contract", "key": "|".join(atoms), "atoms": atoms, "raw": it.get("canonical")})
    for d in final.get("deadlines") or []:
        if d.get("kind") == "date" and _iso_to_key(d.get("date")):
            out.append({"cat": "date", "key": d["date"], "raw": d.get("raw")})
        elif d.get("amount") is not None and d.get("unit") in UNIT_KIND:
            k = UNIT_KIND[d["unit"]]
            out.append({"cat": "days", "key": f"{d['amount']}:{k}", "n": d["amount"], "days_kind": k, "raw": d.get("raw")})
    for op in final.get("operations") or []:
        if _iso_to_key(op.get("date")):
            out.append({"cat": "date", "key": op["date"], "raw": op.get("raw")})
        if op.get("amount"):
            out.append({"cat": "sum", "key": f"{float(op['amount']):.2f}", "raw": op.get("raw")})
    p = final.get("period")
    if isinstance(p, dict):
        for k in ("from", "to"):
            if _iso_to_key(p.get(k)):
                out.append({"cat": "date", "key": p[k], "raw": p.get("raw")})
        rel = p.get("relative") or {}
        if rel.get("unit") == "days" and rel.get("amount"):
            out.append({"cat": "days", "key": f"{rel['amount']}:unspecified", "n": rel["amount"], "days_kind": "unspecified",
                        "raw": p.get("raw")})
    rm = (final.get("request_meta") or {}).get("date")
    if isinstance(rm, dict) and _iso_to_key(rm.get("value")):
        out.append({"cat": "date", "key": rm["value"], "raw": rm.get("value")})
    for r in (final.get("appeal") or {}).get("routes") or []:
        if r.get("type") in ROUTE_ORG:
            out.append({"cat": "org", "key": ROUTE_ORG[r["type"]], "raw": r.get("type")})
    return dedup(out)


# ---------- 4. Сборка

CAT_LABEL = {"norm_law": "норма закона (ст./п./ч.)", "norm_contract": "пункт договора/правил", "law": "закон (115-ФЗ/161-ФЗ)",
             "date": "дата", "days": "срок в днях", "sum": "сумма", "org": "орган / маршрут (МВК, ЦБ, суд, РФМ)"}


def check_facts(facts: list[dict], src: Source) -> list[dict]:
    out = []
    for f in facts:
        ok, why = src.has(f)
        out.append({**f, "in_text": ok, "why": why})
    return out


def eval_diy(item: dict) -> dict:
    meta, resp = diy_read(item["id"])
    text = item["text"]
    claims, cells = parse_claims(resp)
    cl = []
    seen = set()
    n_raw = 0
    for c in claims:
        if not is_claim(c):
            continue
        n_raw += 1
        key = re.sub(r"\s+", " ", c["text"].lower()).strip()
        if key in seen:  # повтор того же утверждения (зацикливание) считаем один раз
            continue
        seen.add(key)
        q = support_locate(c["text"], text)
        cl.append({**c, "support": q, "supported": q is not None, "supported_soft": support_tokens(c["text"], text),
                   "advice": is_advice(c)})
    ce = []
    for c in cells:
        if not is_claim(c):
            continue
        q = support_locate(c["text"], text)
        ce.append({**c, "supported": q is not None})
    facts = check_facts(facts_from_text(resp), Source(text))
    return {"meta": meta, "has_table": bool(cells), "claims": cl, "claims_with_repeats": n_raw, "cells": ce, "facts": facts}


def eval_ours(item: dict) -> dict:
    from navigator.validator import validate
    rec = json.loads((OURS_DIR / f"{item['id']}.json").read_text(encoding="utf-8"))
    text = nfc(item["text"])
    fields = []
    n_quotes = n_quotes4 = 0
    for path, evs in ours_fields(rec["final"]):
        ok = bool(evs)
        for e in evs:
            n_quotes += 1
            n_quotes4 += len(e.get("quote", "").split()) >= 4
            if not (check_span(text, e) and locate(text, e.get("quote", ""))):
                ok = False
        fields.append({"path": path, "supported": ok})
    facts = check_facts(ours_facts(rec["final"]), Source(text))
    _, raw_rep = validate(rec["llm_raw"], text)  # тот же LLM со схемой, но до валидатора
    raw_facts = check_facts(ours_facts(rec["llm_raw"]), Source(text))  # LLM со схемой, без правил и валидатора
    return {"fields": fields, "facts": facts, "llm_raw_facts": raw_facts, "n_quotes": n_quotes, "n_quotes_ge4": n_quotes4,
            "llm_seconds": rec["llm_meta"].get("seconds"), "llm_source": rec["llm_source"],
            "llm_raw_dropped_quotes": raw_rep.dropped_quotes, "llm_raw_dropped_fields": raw_rep.dropped_fields,
            "llm_raw_schema_errors": raw_rep.schema_errors, "llm_error": rec["llm_meta"].get("error")}


def _share(a: int, b: int) -> str:
    return f"{a}/{b} = {a / b:.0%}" if b else f"{a}/0"


def report(items: list[dict]) -> int:
    rows = []
    for it in items:
        rows.append({"id": it["id"], "bank": it["bank"], "diy": eval_diy(it), "ours": eval_ours(it)})

    def tot(fn):
        return sum(fn(r) for r in rows)

    d_cl = tot(lambda r: len(r["diy"]["claims"]))
    d_cl_un = tot(lambda r: sum(not c["supported"] for c in r["diy"]["claims"]))
    d_cl_un_soft = tot(lambda r: sum(not c["supported_soft"] for c in r["diy"]["claims"]))
    d_cl_na = tot(lambda r: sum(not c["advice"] for c in r["diy"]["claims"]))
    d_cl_na_un = tot(lambda r: sum((not c["advice"]) and not c["supported"] for c in r["diy"]["claims"]))
    d_ce = tot(lambda r: len(r["diy"]["cells"]))
    d_ce_un = tot(lambda r: sum(not c["supported"] for c in r["diy"]["cells"]))
    d_ce_na = tot(lambda r: sum(not c["advice"] for c in r["diy"]["cells"]))
    d_ce_na_un = tot(lambda r: sum((not c["advice"]) and not c["supported"] for c in r["diy"]["cells"]))
    o_f = tot(lambda r: len(r["ours"]["fields"]))
    o_f_un = tot(lambda r: sum(not f["supported"] for f in r["ours"]["fields"]))

    def fact_stats(side: str) -> dict:
        st: dict[str, list[int]] = {}
        for r in rows:
            for f in r[side]["facts"]:
                s = st.setdefault(f["cat"], [0, 0, 0])  # всего, не из текста, текстов с «не из текста»
                s[0] += 1
                s[1] += not f["in_text"]
            for cat in {f["cat"] for f in r[side]["facts"] if not f["in_text"]}:
                st[cat][2] += 1
        return st

    fd, fo = fact_stats("diy"), fact_stats("ours")
    d_days_n = tot(lambda r: sum(f["cat"] == "days" and not f["in_text"] and f["why"].startswith("числа") for f in r["diy"]["facts"]))
    d_days_k = tot(lambda r: sum(f["cat"] == "days" and not f["in_text"] and f["why"].startswith("добавлен") for f in r["diy"]["facts"]))
    secs = sorted(r["diy"]["meta"]["seconds"] for r in rows)
    o_secs = sorted(r["ours"]["llm_seconds"] for r in rows if r["ours"]["llm_seconds"] is not None)
    d_txt_inv = sum(any(not f["in_text"] for f in r["diy"]["facts"]) for r in rows)
    o_txt_inv = sum(any(not f["in_text"] for f in r["ours"]["facts"]) for r in rows)
    raw_dq = tot(lambda r: len(r["ours"]["llm_raw_dropped_quotes"]))
    raw_df = tot(lambda r: len(r["ours"]["llm_raw_dropped_fields"]))
    rf_all = tot(lambda r: len(r["ours"]["llm_raw_facts"]))
    rf_bad = tot(lambda r: sum(not f["in_text"] for f in r["ours"]["llm_raw_facts"]))
    rf_txt = sum(any(not f["in_text"] for f in r["ours"]["llm_raw_facts"]) for r in rows)

    summary = {
        "n_texts": len(rows), "ids": [r["id"] for r in rows],
        "diy": {"claims": d_cl, "claims_unsupported": d_cl_un, "claims_unsupported_soft": d_cl_un_soft,
                "claims_no_advice": d_cl_na, "claims_no_advice_unsupported": d_cl_na_un,
                "texts_with_table": sum(r["diy"]["has_table"] for r in rows),
                "cells": d_ce, "cells_unsupported": d_ce_un, "cells_no_advice": d_ce_na, "cells_no_advice_unsupported": d_ce_na_un,
                "facts": {k: {"total": v[0], "not_in_text": v[1], "texts": v[2]} for k, v in fd.items()},
                "days_number_absent": d_days_n, "days_kind_added": d_days_k, "texts_with_invented_fact": d_txt_inv,
                "claims_with_repeats": tot(lambda r: r["diy"]["claims_with_repeats"]),
                "seconds_median": secs[len(secs) // 2], "seconds_max": secs[-1],
                "truncated": [r["id"] for r in rows if r["diy"]["meta"].get("done_reason") != "stop"]},
        "ours": {"fields": o_f, "fields_unsupported": o_f_un,
                 "quotes": tot(lambda r: r["ours"]["n_quotes"]), "quotes_ge4_words": tot(lambda r: r["ours"]["n_quotes_ge4"]),
                 "facts": {k: {"total": v[0], "not_in_text": v[1], "texts": v[2]} for k, v in fo.items()},
                 "llm_raw_dropped_quotes": raw_dq, "llm_raw_dropped_fields": raw_df, "texts_with_invented_fact": o_txt_inv,
                 "llm_raw_facts": rf_all, "llm_raw_facts_not_in_text": rf_bad, "llm_raw_texts_with_invented_fact": rf_txt,
                 "llm_seconds_median": o_secs[len(o_secs) // 2] if o_secs else None,
                 "llm_from_cache": sum(r["ours"]["llm_source"].startswith("eval/cache") for r in rows),
                 "llm_errors": [r["id"] for r in rows if r["ours"]["llm_error"]]},
    }
    (DIY_DIR / "results.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")

    def ftot(st: dict, cats=None) -> tuple[int, int]:
        ks = [k for k in st if cats is None or k in cats]
        return sum(st[k][0] for k in ks), sum(st[k][1] for k in ks)

    L = ["# DIY против конвейера — сводка (генерируется `eval/diy/run_diy.py`)", "",
         f"Тексты: {len(rows)} дословных из `data/real/corpus.jsonl` ({', '.join(r['id'] for r in rows)}).", "",
         "## Опора на текст", "", "| | DIY (промпт №1 Клерка) | Наш конвейер |", "|---|---|---|",
         f"| Утверждения / поля без дословной опоры | {_share(d_cl_un, d_cl)} | {_share(o_f_un, o_f)} |",
         f"| То же без ответов на «советные» вопросы промпта | {_share(d_cl_na_un, d_cl_na)} | — |",
         f"| То же, мягкая проверка (без учёта пунктуации) | {_share(d_cl_un_soft, d_cl)} | — |",
         f"| Ячейки таблиц без опоры (если таблица была) | {_share(d_ce_un, d_ce)}; без колонок-советов {_share(d_ce_na_un, d_ce_na)} | — |",
         f"| Ответов с таблицей | {summary['diy']['texts_with_table']}/{len(rows)} | — |", "",
         "## Факты не из текста (нормы, законы, даты, сроки, суммы, органы)", "",
         "| Вид | DIY: не из текста / всего (текстов) | Наш: не из текста / всего (текстов) |", "|---|---|---|"]
    for cat, label in CAT_LABEL.items():
        a, b = fd.get(cat, [0, 0, 0]), fo.get(cat, [0, 0, 0])
        L.append(f"| {label} | {a[1]}/{a[0]} ({a[2]}) | {b[1]}/{b[0]} ({b[2]}) |")
    a, b = ftot(fd), ftot(fo)
    a2, b2 = ftot(fd, set(CAT_LABEL) - {"law"}), ftot(fo, set(CAT_LABEL) - {"law"})
    L += [f"| **Итого** | {_share(a[1], a[0])} | {_share(b[1], b[0])} |",
          f"| Итого без строки «закон» | {_share(a2[1], a2[0])} | {_share(b2[1], b2[0])} |", "",
          f"Текстов, где есть хотя бы один факт не из текста: DIY {d_txt_inv}/{len(rows)}, наш конвейер {o_txt_inv}/{len(rows)}.", "",
          f"Сроки DIY не из текста: числа дней нет в тексте — {d_days_n}; к сроку из текста добавлен вид дней — {d_days_k}.", "",
          f"Утверждения DIY считаются уникальными внутри ответа: {d_cl} уникальных из {summary['diy']['claims_with_repeats']} с повторами.", "",
          f"Наш конвейер до валидатора (тот же LLM со схемой): цитат не найдено в тексте — {raw_dq}, полей обнулено — {raw_df}; "
          f"фактов не из текста — {_share(rf_bad, rf_all)} в {rf_txt} текстах; в итоговом результате таких фактов осталось "
          f"{ftot(fo)[1]}.", "",
          f"Наш конвейер: ответ LLM из eval/cache — {summary['ours']['llm_from_cache']}/{len(rows)}; вызов LLM упал (тогда работают "
          f"только правила) — {summary['ours']['llm_errors'] or 'нет'}; время LLM: медиана {summary['ours']['llm_seconds_median']} с.", "",
          f"Время ответа DIY: медиана {summary['diy']['seconds_median']:.0f} с, максимум {summary['diy']['seconds_max']:.0f} с. "
          f"Обрезанные ответы: {summary['diy']['truncated'] or 'нет'}.", "",
          "## По текстам", "",
          "| ID | Банк | DIY: утв. без опоры | DIY: фактов не из текста | DIY: нормы не из текста | DIY: сроки не из текста | "
          "Наш: поля без опоры | Наш: факты не из текста | DIY, с |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d, o = r["diy"], r["ours"]
        dn = [f["raw"] for f in d["facts"] if f["cat"] in ("norm_law", "norm_contract") and not f["in_text"]]
        dd = [f["raw"] for f in d["facts"] if f["cat"] == "days" and not f["in_text"]]
        L.append(f"| {r['id']} | {r['bank']} | {sum(not c['supported'] for c in d['claims'])}/{len(d['claims'])} | "
                 f"{sum(not f['in_text'] for f in d['facts'])}/{len(d['facts'])} | {'; '.join(dn) or '—'} | {'; '.join(dd) or '—'} | "
                 f"{sum(not f['supported'] for f in o['fields'])}/{len(o['fields'])} | "
                 f"{sum(not f['in_text'] for f in o['facts'])}/{len(o['facts'])} | {d['meta']['seconds']:.0f} |")
    L += ["", "## Все факты DIY не из текста", ""]
    for r in rows:
        for f in r["diy"]["facts"]:
            if not f["in_text"]:
                L.append(f"- {r['id']}: {CAT_LABEL[f['cat']]} «{f['raw']}» {f['why']}".rstrip())
    L += ["", "## Все факты нашего конвейера не из текста", ""]
    bad = [(r["id"], f) for r in rows for f in r["ours"]["facts"] if not f["in_text"]]
    L += [f"- {i}: {CAT_LABEL[f['cat']]} «{f['raw']}» {f['why']}".rstrip() for i, f in bad] or ["- нет"]
    L += ["", "## LLM со схемой до валидатора: факты не из текста (валидатор их обнулил)", ""]
    bad = [(r["id"], f) for r in rows for f in r["ours"]["llm_raw_facts"] if not f["in_text"]]
    L += [f"- {i}: {CAT_LABEL[f['cat']]} «{f['raw']}» {f['why']}".rstrip() for i, f in bad] or ["- нет"]
    (DIY_DIR / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:30]))
    print(f"→ {(DIY_DIR / 'summary.md').relative_to(ROOT)}, {(DIY_DIR / 'results.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
