"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { LineStops } from "@/components/LineStops";
import { RouteGroups, planRoutes } from "@/components/RouteGroups";
import { ArrowSign, BarSign, HereSign } from "@/components/Signs";
import { api, type Evidence, type Extraction, type PackageResult, type Routes } from "@/lib/api";
import { APPEAL, CHANNEL, DOC, ELEMENTS, ELEMENT_OK, ELEMENT_PARTIAL, LEGAL_LEVEL, MEASURE, SCENARIO, SCENARIO_NOTE, ruDate } from "@/lib/labels";
import { useCase } from "@/lib/store";

type Sample = { id: string; title: string; kind: string; note: string; source: string | null; text: string };
type Field = { key: string; title: string; body: ReactNode; gap: string | null; evs: Evidence[] };
type Anchor = { key: string; title: string; evs: Evidence[] };

/** Пункты запроса как отдельные якоря: пункт чек-листа ↔ его цитата в письме. */
function itemAnchors(x: Extraction): Anchor[] {
  return x.requested_items.map((i, n) => ({ key: `item-${n}`, title: `Что собрать: ${DOC[i.type] ?? i.type}`, evs: i.evidence }));
}

/** Поле «Что просят» и пункты чек-листа подсвечивают друг друга. */
function linked(a: string | null, key: string): boolean {
  if (!a) return false;
  if (a === key) return true;
  if (a === "asked") return key.startsWith("item-");
  return key === "asked" && a.startsWith("item-");
}

function fieldsOf(x: Extraction): Field[] {
  const f: Field[] = [];
  const ev = (o: { evidence: Evidence[] } | null | undefined) => (o ? o.evidence : []);
  const sc = x.scenario.value;
  f.push({
    key: "measure",
    title: "Мера",
    body: (
      <p>
        {SCENARIO[sc] ?? sc}
        {x.measures.length > 0 ? <>. В тексте: {x.measures.map((m) => MEASURE[m.type] ?? m.type).join(", ")}.</> : null}
      </p>
    ),
    gap: x.measures.length || x.scenario.evidence.length ? null : "Банк не назвал меру прямо. По письму Банка России ИН-01-59/98 вид меры сообщается всегда.",
    evs: [...ev(x.scenario), ...x.measures.flatMap(ev)],
  });
  f.push({
    key: "norm",
    title: "Норма",
    body: (
      <p>
        <b>{x.legal_basis.items.map((i) => i.canonical).join("; ")}</b> ({LEGAL_LEVEL[x.legal_basis.level]})
      </p>
    ),
    gap: x.legal_basis.items.length
      ? null
      : "Ни статьи закона, ни пункта договора. По письму Банка России ИН-01-59/98 банку необходимо назвать закон с конкретной нормой и (или) условие договора.",
    evs: x.legal_basis.items.flatMap(ev),
  });
  f.push({
    key: "reason",
    title: "Причина",
    body: <p>{x.reason.text} ({x.reason.level === "specific" ? "конкретная" : "общая формулировка"})</p>,
    gap: x.reason.level === "none" ? "Причина не названа. По письму ИН-01-59/98 банк сообщает причины решения." : null,
    evs: ev(x.reason),
  });
  f.push({
    key: "asked",
    title: "Что просят",
    body: (
      <>
        <ul>
          {x.requested_items.map((i, n) => (
            <li key={n}>
              {DOC[i.type] ?? i.type}
              {i.format ? `, ${i.format}` : ""}
            </li>
          ))}
        </ul>
        {x.period ? <p>Период: {x.period.raw}</p> : null}
      </>
    ),
    gap: x.requested_items.length ? null : "Перечень документов в тексте не указан.",
    // Цитаты пунктов запроса привязаны к пунктам чек-листа «Что собрать» (item-N), у поля только период.
    evs: ev(x.period),
  });
  const cd = x.deadlines.filter((d) => d.applies_to === "client_response");
  const bd = x.deadlines.filter((d) => d.applies_to === "bank_review");
  f.push({
    key: "deadline",
    title: "Ближайший срок",
    body: (
      <>
        {cd.map((d, n) => (
          <p key={n}>
            Ответить: <b>{d.raw}</b>
            {d.date && !d.raw.includes(ruDate(d.date)) ? ` (${ruDate(d.date)})` : ""}
          </p>
        ))}
        {bd.map((d, n) => (
          <p key={`b${n}`}>Банк рассматривает: {d.raw}</p>
        ))}
      </>
    ),
    gap: x.deadlines.length
      ? null
      : sc === "doc_request"
        ? "Законного срока ответа на запрос нет, его задаёт банк (Методичка ЦБ, с. 15). Уточните срок у банка."
        : "Срок в тексте не указан. Законные сроки для вашей меры на следующем шаге.",
    evs: x.deadlines.flatMap(ev),
  });
  f.push({
    key: "channel",
    title: "Канал связи",
    body: <p>{x.response_channels.map((c) => CHANNEL[c.type] ?? c.type).join(", ")}</p>,
    gap: x.response_channels.length ? null : "Канал не указан. При ограничении интернет-банка банк сохраняет канал связи (ИН-03-59/11).",
    evs: x.response_channels.flatMap(ev),
  });
  f.push({
    key: "next",
    title: "Что сделать, по тексту банка",
    body: <p>{x.next_steps.text}</p>,
    gap: x.next_steps.stated ? null : "Банк не объяснил, что сделать, чтобы снять меру (ИН-01-59/98).",
    evs: ev(x.next_steps),
  });
  f.push({
    key: "appeal",
    title: "Обжалование, по тексту банка",
    body: (
      <p>
        {x.appeal.routes.map((r) => APPEAL[r.type] ?? r.type).join(", ")}
        {x.appeal.explicit_denial ? <> Банк пишет: «{x.appeal.explicit_denial.value}».</> : null}
      </p>
    ),
    gap: x.appeal.routes.length || x.appeal.explicit_denial ? null : "Порядок обжалования не указан. Допустимые маршруты ниже.",
    evs: [...x.appeal.routes.flatMap(ev), ...ev(x.appeal.explicit_denial)],
  });
  if (x.consequences.length)
    f.push({ key: "conseq", title: "Если не ответить", body: <p>{[...new Set(x.consequences.map((c) => c.evidence[0]?.quote ?? c.raw))].map((q) => `«${q}»`).join("; ")}</p>, gap: null, evs: x.consequences.flatMap(ev) });
  if (x.operations.length)
    f.push({ key: "ops", title: "Операция", body: <p>{x.operations.map((o) => o.raw).join("; ")}</p>, gap: null, evs: x.operations.flatMap(ev) });
  return f;
}

type Span = { start: number; end: number; key: string };
function spansOf(fields: Anchor[]): Span[] {
  const all: Span[] = [];
  for (const f of fields) for (const e of f.evs) if (e.start !== undefined && e.end !== undefined && e.end > e.start) all.push({ start: e.start, end: e.end, key: f.key });
  all.sort((a, b) => a.start - b.start || b.end - a.end);
  const out: Span[] = [];
  let pos = 0;
  for (const s of all) if (s.start >= pos) { out.push(s); pos = s.end; }
  return out;
}

// Дата «сегодня» в часовом поясе пользователя, в формате ГГГГ-ММ-ДД, как даты в разборе.
function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Razbor() {
  const { state, update } = useCase();
  const [samples, setSamples] = useState<Sample[]>([]);
  const [draft, setDraft] = useState("");
  const [rulesOnly, setRulesOnly] = useState(false);
  const [phase, setPhase] = useState<"empty" | "loading" | "error" | "result">("empty");
  const [inputError, setInputError] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [routes, setRoutes] = useState<Routes | null>(null);
  const [rise, setRise] = useState(false);
  const ticketRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch("/samples.json")
      .then((r) => r.json())
      .then((d) => setSamples(d.samples as Sample[]))
      .catch(() => setSamples([]));
  }, []);

  useEffect(() => {
    if (state.parse) {
      setPhase("result");
      setDraft(state.text);
    }
  }, [state.parse, state.text]);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("sample");
    if (id && samples.length) {
      const s = samples.find((x) => x.id === id);
      if (s && !state.parse) {
        setDraft(s.text);
        update({ sampleId: s.id });
      }
    }
  }, [samples, state.parse, update]);

  const scenario = state.parse?.extraction.scenario.value;
  useEffect(() => {
    if (!scenario) return;
    api.routes(scenario, false).then(setRoutes).catch(() => setRoutes(null));
  }, [scenario]);

  const fields = useMemo(() => (state.parse ? fieldsOf(state.parse.extraction) : []), [state.parse]);
  const anchors = useMemo<Anchor[]>(() => (state.parse ? [...fields, ...itemAnchors(state.parse.extraction)] : []), [fields, state.parse]);
  const spans = useMemo(() => spansOf(anchors), [anchors]);
  // Кнопка «Показать в письме» только у полей, чья цитата реально выделена (пересекающиеся цитаты уступают более ранней).
  const markedKeys = useMemo(() => {
    const k = new Set(spans.map((s) => s.key));
    if ([...k].some((x) => x.startsWith("item-"))) k.add("asked");
    return k;
  }, [spans]);

  // Чек-лист пакета (/api/v1/package): пункты самого запроса банка; отметки только в браузере.
  const [pack, setPack] = useState<PackageResult | null>(null);
  const [packPhase, setPackPhase] = useState<"idle" | "loading" | "error" | "ok">("idle");
  const packHead = useRef<HTMLHeadingElement>(null);
  const loadPack = useCallback(() => {
    if (!state.parse) return;
    setPackPhase("loading");
    api
      .package(state.parse.extraction)
      .then((p) => {
        setPack(p);
        setPackPhase("ok");
      })
      .catch(() => setPackPhase("error"));
  }, [state.parse]);
  useEffect(() => {
    if (state.parse) loadPack();
    else {
      setPack(null);
      setPackPhase("idle");
    }
  }, [state.parse, loadPack]);

  const run = useCallback(
    async (text: string) => {
      setPhase("loading");
      setError("");
      setActive(null);
      try {
        const [parse, guard] = await Promise.all([api.parse(text, rulesOnly ? "rules" : "hybrid"), api.guard(text)]);
        update({ text, parse, guard, events: {}, firstLevel: false, values: {}, packed: {} });
        setRise(true);
        setPhase("result");
      } catch (e) {
        // Сетевой сбой браузер описывает по-английски («Failed to fetch»): показываем только ответы сервера.
        setError(e instanceof Error && e.message.startsWith("Сервер ответил") ? e.message.replace("Сервер ответил", "код ответа") : "");
        setPhase("error");
      }
    },
    [rulesOnly, update],
  );

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = draft.trim();
    if (!t) {
      setInputError(true);
      fieldRef.current?.focus();
      return;
    }
    setInputError(false);
    void run(t);
  };

  const pick = (s: Sample) => {
    setDraft(s.text);
    setInputError(false);
    update({ sampleId: s.id });
  };

  const show = (key: string) => {
    setActive(key);
    requestAnimationFrame(() => {
      const sel = key === "asked" ? `mark[data-f="asked"], mark[data-f^="item-"]` : `mark[data-f="${key}"]`;
      const m = ticketRef.current?.querySelector<HTMLElement>(sel);
      m?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });
  };

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setActive(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const markKey = (e: KeyboardEvent<HTMLElement>, key: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setActive(key);
    }
  };

  const [wantFocus, setWantFocus] = useState(false);
  useEffect(() => {
    if (wantFocus && phase === "empty") {
      fieldRef.current?.focus();
      setWantFocus(false);
    }
  }, [wantFocus, phase]);

  const another = () => {
    // Убираем ?sample= из адреса, иначе пример подставится снова.
    if (window.location.search) window.history.replaceState(null, "", window.location.pathname);
    update({ parse: null, guard: null, text: "", sampleId: null, events: {}, values: {}, packed: {} });
    setDraft("");
    setPhase("empty");
    setRoutes(null);
    setWantFocus(true);
  };

  const sample = samples.find((s) => s.id === state.sampleId);
  const text = state.text;
  const meta = state.parse?.meta;
  const guard = state.guard;

  return (
    <div className="page">
      <LineStops here="razbor" enabled={Boolean(state.parse)} />
      <div className="page-head">
        <h1>Разбор письма банка</h1>
        <p>Вставьте текст уведомления или запроса. Персональные данные для разбора не нужны: удалите ИНН, номера счетов и ФИО, если они есть.</p>
      </div>

      {phase === "empty" && (
        <form className="paste" onSubmit={submit} noValidate>
          {samples.length > 0 && (
            <div className="samples" role="group" aria-label="Примеры писем">
              {samples.map((s) => (
                <button type="button" key={s.id} className="sample" aria-pressed={state.sampleId === s.id && draft === s.text} onClick={() => pick(s)}>
                  <b>{s.title}</b>
                  <span>{s.kind === "real" ? "реальный текст, ПДн удалены" : "синтетика"}</span>
                </button>
              ))}
            </div>
          )}
          <label htmlFor="letter" className="field-label">
            Текст уведомления или запроса банка
          </label>
          <p className="hint" id="letter-hint">
            Сообщение из чата банка, SMS или письмо.
          </p>
          <textarea
            id="letter"
            ref={fieldRef}
            rows={8}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-describedby={inputError ? "letter-hint letter-error" : "letter-hint"}
            aria-invalid={inputError}
            spellCheck={false}
            placeholder="Вставьте текст сюда"
          />
          {inputError && (
            <p className="error-text" id="letter-error" role="alert">
              Вставьте текст письма, чтобы его разобрать.
            </p>
          )}
          <label className="check">
            <input type="checkbox" checked={rulesOnly} onChange={(e) => setRulesOnly(e.target.checked)} />
            Только правила, без модели: быстрее, но слабее на сложных текстах
          </label>
          <div className="cta-row">
            <button type="submit" className="btn btn-primary">
              Разобрать письмо банка
            </button>
          </div>
        </form>
      )}

      {phase === "loading" && (
        <div>
          <p className="loading-text" role="status">
            {rulesOnly
              ? "Разбираем текст правилами."
              : "Читаем письмо: правила и модель на сервере команды ищут меру, норму, сроки и цитаты. На тестовом ноутбуке обычно около 20 секунд (медиана 18,6 с); если модель не ответит за 90 секунд, текст разберут правила."}
          </p>
          <div className="progress" aria-hidden="true">
            <span className="progress-bar" />
          </div>
        </div>
      )}

      {phase === "error" && (
        <div className="error-box" role="alert">
          <p className="error-title">Не удалось разобрать текст</p>
          <p>Сервер не ответил{error ? ` (${error})` : ""}. Текст сохранён, попробуйте ещё раз.</p>
          <div className="cta-row">
            <button type="button" className="btn btn-primary" onClick={() => void run(draft.trim())}>
              Повторить разбор
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setPhase("empty")}>
              Вернуться к тексту
            </button>
          </div>
        </div>
      )}

      {phase === "result" && state.parse && (
        <div>
          {sample && sample.text === text && (
            <p className="source-line">
              Пример: {sample.note}.{" "}
              {sample.source ? (
                <>
                  Источник:{" "}
                  <a href={sample.source} rel="noopener">
                    {new URL(sample.source).hostname}
                  </a>
                  .
                </>
              ) : null}
            </p>
          )}
          {meta?.fallback && <p className="notice">Модель недоступна, текст разобран правилами. Сложные поля могли остаться пустыми.</p>}
          {meta?.injection_detected && (
            <p className="notice">В тексте есть инструкции для программы. Мы их не выполняем: текст только разбирается, каждое поле с цитатой.</p>
          )}

          <div className="sign sign-here">
            <HereSign />
            <div>
              <p className="here-label">Вы здесь</p>
              <h2 className="here-title">{SCENARIO[state.parse.extraction.scenario.value] ?? "Мера не определена"}</h2>
              <p className="here-sub">{SCENARIO_NOTE[state.parse.extraction.scenario.value]}</p>
            </div>
          </div>

          {(() => {
            const x = state.parse.extraction;
            const step = routes ? planRoutes(routes).now : null;
            const cd = x.deadlines.find((d) => d.applies_to === "client_response");
            const hasItems = x.requested_items.length > 0;
            return (
              <section className="next-step" aria-label="Следующий шаг">
                <p>
                  <span className="next-label">Следующий шаг:</span>
                  {step ? <>{step.title}, </> : null}
                  {cd?.date && cd.date < todayIso() ? (
                    <span className="next-when unknown">срок из письма {ruDate(cd.date)} уже прошёл, уточните у банка, принимает ли он ответ</span>
                  ) : cd?.date ? (
                    <span className="next-when">до {ruDate(cd.date)}</span>
                  ) : cd ? (
                    <span className="next-when unknown">срок по письму: «{cd.raw}»</span>
                  ) : (
                    <span className="next-when unknown">срок в письме не указан, уточните у банка</span>
                  )}
                </p>
                {hasItems ? (
                  <a
                    className="btn btn-primary"
                    href="#sobrat"
                    onClick={(e) => {
                      e.preventDefault();
                      const h = packHead.current;
                      h?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
                      h?.focus({ preventScroll: true });
                    }}
                  >
                    Собрать пакет
                  </a>
                ) : (
                  <Link className="btn btn-primary" href="/marshrut/">
                    Посчитать срок
                  </Link>
                )}
              </section>
            );
          })()}

          <p className="help-line">
            Нажмите «Показать в письме» у поля или выделенный фрагмент письма: они связаны. Esc снимает выделение. Разобрано:{" "}
            {meta?.mode === "rules" ? "правила" : meta?.fallback ? "правила (модель недоступна)" : "правила и модель T-lite-it-2.1"}
            {meta?.seconds ? `, ${meta.seconds.toFixed(0)} с` : ""}.
          </p>

          <div className="desk">
            <div className="panels" aria-label="Поля карточки">
              {fields.map((f) => (
                <article key={f.key} className={`panel${f.gap ? " panel-gap" : ""}${linked(active, f.key) ? " is-active" : ""}`}>
                  <h3>{f.title}</h3>
                  {f.gap ? (
                    <>
                      <p className="gap">
                        <BarSign />
                        Не указано банком
                      </p>
                      <p>{f.gap}</p>
                    </>
                  ) : (
                    <>
                      {f.body}
                      {markedKeys.has(f.key) && (
                        <button type="button" className="link-btn" onClick={() => show(f.key)} aria-pressed={linked(active, f.key)} aria-label={`Показать в письме: ${f.title}`}>
                          Показать в письме
                        </button>
                      )}
                    </>
                  )}
                </article>
              ))}
            </div>

            <article className="ticket" aria-labelledby="ticket-title" ref={ticketRef}>
              <h2 id="ticket-title" className="ticket-title">
                Текст банка
              </h2>
              <p>
                {(() => {
                  const out: ReactNode[] = [];
                  let pos = 0;
                  spans.forEach((s, i) => {
                    if (s.start > pos) out.push(text.slice(pos, s.start));
                    out.push(
                      <mark
                        key={i}
                        className={`q${linked(active, s.key) ? " is-active" : ""}`}
                        data-f={s.key}
                        role="button"
                        tabIndex={0}
                        aria-pressed={linked(active, s.key)}
                        aria-label={`${anchors.find((f) => f.key === s.key)?.title ?? "Поле"}: ${text.slice(s.start, s.end)}`}
                        onClick={() => setActive(s.key)}
                        onKeyDown={(e) => markKey(e, s.key)}
                      >
                        {text.slice(s.start, s.end)}
                      </mark>,
                    );
                    pos = s.end;
                  });
                  out.push(text.slice(pos));
                  return out;
                })()}
              </p>
            </article>
          </div>

          {(state.parse.extraction.requested_items.length > 0 || state.parse.extraction.scenario.value === "doc_request") && (
            <section className="pack" id="sobrat" aria-labelledby="h-pack">
              <h2 id="h-pack" ref={packHead} tabIndex={-1}>
                Что собрать
              </h2>
              <p className="side-src">
                Пункты взяты из текста вашего банка, у каждого цитата. Отметки хранятся только в этом браузере и на сервер не уходят.
              </p>
              {state.parse.extraction.requested_items.length === 0 && (
                <p className="notice">Банк не перечислил документы в тексте. Уточните у банка перечень, период и формат.</p>
              )}
              {packPhase === "loading" && (
                <p role="status" className="loading-text">
                  Собираем чек-лист по пунктам запроса.
                </p>
              )}
              {packPhase === "error" && (
                <div className="error-box" role="alert">
                  <p className="error-title">Чек-лист не загрузился</p>
                  <p>Сервер не ответил. Пункты запроса есть в поле «Что просят» выше.</p>
                  <button type="button" className="btn btn-quiet" onClick={loadPack}>
                    Загрузить чек-лист ещё раз
                  </button>
                </div>
              )}
              {packPhase === "ok" && pack && (
                <>
                  {pack.items.length > 0 && (
                    <>
                      <p className="pack-count" aria-live="polite">
                        Отмечено: {pack.items.filter((it) => state.packed[it.index]).length} из {pack.items.length}
                      </p>
                      <ul className="pack-list">
                        {pack.items.map((it) => {
                          const src = state.parse!.extraction.requested_items[it.index];
                          const quote = src?.evidence[0]?.quote ?? it.raw;
                          const key = `item-${it.index}`;
                          const id = `pk-${it.index}`;
                          return (
                            <li key={it.index} className={linked(active, key) ? "is-active" : ""}>
                              <input
                                type="checkbox"
                                id={id}
                                checked={Boolean(state.packed[it.index])}
                                onChange={(e) => update({ packed: { ...state.packed, [it.index]: e.target.checked } })}
                              />
                              <div className="pack-item-body">
                                <label htmlFor={id}>
                                  {DOC[it.type] ?? it.type}
                                  {src?.format ? `, ${src.format}` : ""}
                                </label>
                                <p className="pack-quote">
                                  В письме: <q>{quote}</q>
                                </p>
                                {markedKeys.has(key) && (
                                  <button type="button" className="link-btn" onClick={() => show(key)} aria-pressed={linked(active, key)} aria-label={`Показать в письме: ${DOC[it.type] ?? it.type}`}>
                                    Показать в письме
                                  </button>
                                )}
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                      {state.parse.extraction.period && (
                        <p className="pack-quote">
                          Период по письму: <q>{state.parse.extraction.period.raw}</q>
                        </p>
                      )}
                    </>
                  )}
                  {pack.followups.length > 0 && (
                    <div className="followups">
                      <h3>Частые дозапросы: не требование вашего банка</h3>
                      <p className="side-src">Их нет в вашем письме. Это то, что банки нередко запрашивают повторно, по открытым памяткам и отзывам.</p>
                      <ul>
                        {pack.followups.map((f) => (
                          <li key={f.text}>
                            {f.text}
                            <span className="src">Источник: {f.source}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="source-line">
                    {pack.pdn_note} {pack.disclaimer}
                  </p>
                </>
              )}
            </section>
          )}

          {guard && (
            <section className="duty" aria-labelledby="h-duty">
              <h2 id="h-duty">Что банк обязан был сообщить</h2>
              <p className="side-src">По письмам Банка России ИН-01-59/98 и ИН-03-59/11. Проверка правилами по этому тексту.</p>
              <ul className="duty-list duty-plain">
                {ELEMENTS.map((el) => {
                  const v = guard.elements[el.key];
                  const cls = ELEMENT_OK.has(v) ? "yes" : ELEMENT_PARTIAL.has(v) ? "part" : "no";
                  const word = ELEMENT_OK.has(v) ? "есть" : ELEMENT_PARTIAL.has(v) ? "частично" : "нет";
                  return (
                    <li key={el.key} className={cls}>
                      {ELEMENT_OK.has(v) || ELEMENT_PARTIAL.has(v) ? <ArrowSign /> : <BarSign />}
                      <span>
                        <span className="rt">{el.label}</span>
                        <span className="duty-word">
                          <b>{word}</b> · {el.src}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {routes && (
            <section className="routes" aria-labelledby="h-routes">
              <h2 id="h-routes">Маршруты для этой меры</h2>
              <RouteGroups base={routes} rise={rise} onRiseEnd={() => setRise(false)} mvkTail="Заявление вернут без рассмотрения, недели будут потеряны." />
            </section>
          )}

          <div className="actions">
            <Link className="btn btn-quiet" href="/marshrut/">
              Посчитать срок
            </Link>
            <Link className="btn btn-quiet" href="/zayavlenie/">
              Собрать заявление
            </Link>
            <button type="button" className="btn btn-quiet" onClick={another}>
              Разобрать другое письмо
            </button>
          </div>
          <p className="source-line spaced">
            {state.parse.disclaimer}
          </p>
        </div>
      )}
    </div>
  );
}
