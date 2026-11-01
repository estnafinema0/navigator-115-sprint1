"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ArrowSign, BarSign, HereSign } from "@/components/Signs";
import { api, type GuardResult } from "@/lib/api";
import { ELEMENTS, ELEMENT_OK, ELEMENT_PARTIAL } from "@/lib/labels";

type GuardSample = { id: string; title: string; note: string; text: string };

const VERDICT = {
  red: { title: "Отправлять нельзя", sub: "В тексте есть то, что банк раскрывать не должен (п. 6 ст. 7 115‑ФЗ) или что противоречит письмам Банка России." },
  yellow: { title: "Не хватает обязательных элементов", sub: "Клиент не поймёт, что делать и куда обращаться. Дополните текст по письмам ИН-01-59/98 и ИН-03-59/11." },
  green: { title: "Обязательные элементы на месте", sub: "Запрещённого не найдено. Решение об отправке принимает сотрудник." },
  review: { title: "Нужна позиция комплаенса", sub: "Обязательные элементы на месте, запрещённого не найдено. Есть формулировки, по которым решение принимает комплаенс банка: они ниже." },
};

// Жёлтый свет бывает по двум причинам: не хватает элементов или нужна позиция комплаенса (поле review в ответе API).
// E6 (канал) в полноту по API не входит, поэтому и здесь не считается.
function verdictOf(g: GuardResult) {
  if (g.light !== "yellow") return VERDICT[g.light];
  const missing = ELEMENTS.some((el) => el.key !== "E6" && !ELEMENT_OK.has(g.elements[el.key]));
  return !missing && g.review?.length ? VERDICT.review : VERDICT.yellow;
}

function marked(text: string, g: GuardResult): ReactNode[] {
  const spans = [
    ...g.forbidden.flatMap((f) => f.hits.map((h) => ({ ...h, cls: "bad" }))),
    ...(g.review ?? []).flatMap((f) => f.hits.map((h) => ({ ...h, cls: "rev" }))),
    ...Object.values(g.evidence).flat().map((h) => ({ ...h, cls: "ok" })),
  ].sort((a, b) => a.start - b.start || (a.cls === "ok" ? 1 : b.cls === "ok" ? -1 : a.cls === "bad" ? -1 : 1));
  const out: ReactNode[] = [];
  let pos = 0;
  spans.forEach((s, i) => {
    if (s.start < pos) return;
    out.push(text.slice(pos, s.start));
    out.push(
      <mark key={i} className={s.cls}>
        {text.slice(s.start, s.end)}
        {s.cls === "bad" ? <span className="visually-hidden"> (раскрывать нельзя)</span> : s.cls === "rev" ? <span className="visually-hidden"> (нужна позиция комплаенса)</span> : null}
      </mark>,
    );
    pos = s.end;
  });
  out.push(text.slice(pos));
  return out;
}

export default function Strazh() {
  const [samples, setSamples] = useState<GuardSample[]>([]);
  const [text, setText] = useState("");
  const [checked, setChecked] = useState("");
  const [res, setRes] = useState<GuardResult | null>(null);
  const [phase, setPhase] = useState<"empty" | "loading" | "error" | "ok">("empty");
  const [inputError, setInputError] = useState(false);

  useEffect(() => {
    fetch("/samples.json")
      .then((r) => r.json())
      .then((d) => setSamples(d.guard as GuardSample[]))
      .catch(() => setSamples([]));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) {
      setInputError(true);
      return;
    }
    setInputError(false);
    setPhase("loading");
    try {
      setRes(await api.guard(t));
      setChecked(t);
      setPhase("ok");
    } catch {
      setPhase("error");
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>Страж уведомлений для банка</h1>
        <p>
          Проверка текста до отправки клиенту: обязательные элементы по письмам Банка России ИН-01-59/98 и ИН-03-59/11 и то, что
          раскрывать нельзя. Только правила, без модели: результат объясним и одинаков при повторе.
        </p>
      </div>

      <form className="paste" onSubmit={submit} noValidate>
        {samples.length > 0 && (
          <div className="samples" role="group" aria-label="Примеры уведомлений">
            {samples.map((s) => (
              <button type="button" key={s.id} className="sample" aria-pressed={text === s.text} onClick={() => setText(s.text)}>
                <b>{s.title}</b>
                <span>{s.note}</span>
              </button>
            ))}
          </div>
        )}
        <label htmlFor="notice" className="field-label">
          Текст уведомления клиенту
        </label>
        <textarea id="notice" rows={8} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} aria-invalid={inputError} aria-describedby={inputError ? "notice-error" : undefined} />
        {inputError && (
          <p className="error-text" id="notice-error" role="alert">
            Вставьте текст уведомления.
          </p>
        )}
        <div className="cta-row">
          <button type="submit" className="btn btn-primary" disabled={phase === "loading"}>
            Проверить уведомление
          </button>
        </div>
      </form>

      {phase === "loading" && (
        <p role="status" className="loading-text">
          Проверяем текст.
        </p>
      )}
      {phase === "error" && (
        <div className="error-box" role="alert">
          <p className="error-title">Сервер не ответил</p>
          <p>Попробуйте проверить ещё раз.</p>
        </div>
      )}

      {phase === "ok" && res && (
        <section className="routes" aria-labelledby="h-verdict">
          <div className={res.light === "red" ? "sign sign-here" : res.light === "green" ? "sign verdict-ok" : "sign sign-no verdict-wait"}>
            {res.light === "red" ? <HereSign /> : res.light === "green" ? <ArrowSign /> : <BarSign />}
            <div>
              {res.light === "red" && <p className="here-label">Вы здесь</p>}
              <h2 id="h-verdict" className="here-title">
                {verdictOf(res).title}
              </h2>
              <p className="here-sub">{verdictOf(res).sub}</p>
            </div>
          </div>

          {res.forbidden.length > 0 && (
            <ul className="post forbidden-list" aria-label="Что раскрывать нельзя">
              {res.forbidden.map((f) => (
                <li key={f.id} className="no">
                  <BarSign />
                  <span>
                    {f.label}: «{f.hits[0].quote}»<span className="src">{f.basis}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {res.review && res.review.length > 0 && (
            <ul className="post review-list" aria-label="Нужна позиция комплаенса">
              {res.review.map((f) => (
                <li key={f.id} className="no">
                  <BarSign />
                  <span>
                    {f.label}: «{f.hits[0]?.quote}»<span className="src">{f.basis}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}

          <h2 className="block-title">Обязательные элементы</h2>
          <ul className="duty-list">
            {ELEMENTS.map((el) => {
              const v = res.elements[el.key];
              const cls = ELEMENT_OK.has(v) ? "sign" : ELEMENT_PARTIAL.has(v) ? "sign sign-wait" : "sign sign-no";
              const word = ELEMENT_OK.has(v) ? "есть" : ELEMENT_PARTIAL.has(v) ? "частично" : "нет";
              return (
                <li key={el.key} className={cls}>
                  {ELEMENT_OK.has(v) || ELEMENT_PARTIAL.has(v) ? <ArrowSign /> : <BarSign />}
                  <span>
                    <span className="rt">{el.label}</span>
                    <span className="duty-word">
                      {word} · {el.src}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>

          <h2 className="block-title">Текст с пометками</h2>
          <p className="hint">
            Зелёный фон: найденное обязательное. Оранжевый фон с чертой снизу: то, что раскрывать нельзя. Пунктирная рамка: нужна
            позиция комплаенса.
          </p>
          <p className="marked">{marked(checked, res)}</p>
        </section>
      )}
    </div>
  );
}
