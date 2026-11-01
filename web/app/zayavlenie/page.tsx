"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { LineStops } from "@/components/LineStops";
import { api, DocError, type DocBody } from "@/lib/api";
import { ruDate } from "@/lib/labels";
import { useCase } from "@/lib/store";

type Doc = { path: string; file: string; title: string; kind: string; note?: string; needsFirstLevel?: boolean; needsDocsDate?: boolean };

const REFUSALS = ["operation_refusal", "contract_refusal"];
// only: поле показывается только для этих мер (там, где его проверяет API документов).
const FIELDS: { key: string; label: string; type?: "date" | "long"; only?: string[] }[] = [
  { key: "company_name", label: "Заявитель: наименование или ФИО ИП" },
  { key: "company_inn", label: "ИНН" },
  { key: "company_address", label: "Адрес" },
  { key: "company_phone", label: "Телефон" },
  { key: "bank_full_name", label: "Банк: полное наименование" },
  { key: "bank_short", label: "Банк: кратко" },
  { key: "contract_number", label: "Договор счёта: номер" },
  { key: "contract_date", label: "Договор счёта: дата", type: "date" },
  { key: "account_first", label: "Номер счёта" },
  { key: "refusal_date", label: "Дата отказа или ограничения", type: "date" },
  { key: "po_date", label: "Платёжное поручение: дата", type: "date" },
  { key: "po_number", label: "Платёжное поручение: номер" },
  { key: "po_amount", label: "Платёжное поручение: сумма" },
  { key: "po_purpose", label: "Платёжное поручение: назначение" },
  { key: "reasons_letter_date", label: "Письмо банка о причинах: дата", type: "date" },
  { key: "reasons_letter_number", label: "Письмо банка о причинах: номер" },
  { key: "bank_reasons", label: "Причины, которые назвал банк (цитата из письма)", type: "long" },
  { key: "docs_submitted_date", label: "Дата, когда вы представили документы в банк", type: "date" },
  // Дату истечения срока банка считает код по календарю (X-Review-Due-Date), вручную её не вводят.
  { key: "bank_answer_date", label: "Дата ответа банка на ваши документы", type: "date", only: REFUSALS },
  { key: "attachments", label: "Приложения: перечень документов" },
];

function docsFor(scenario: string): Doc[] {
  const d: Doc[] = [];
  if (scenario === "remote_access_restriction")
    d.push({ path: "/api/v1/documents/1", file: "zapros-prichin-ogranicheniya-dbo.docx", title: "Запрос причин ограничения интернет-банка", kind: "Шаблон Банка России № 1" });
  if (scenario === "operation_refusal") {
    d.push({ path: "/api/v1/documents/4", file: "dokumenty-posle-otkaza-p13-4.docx", title: "Документы после отказа в операции (п. 13.4 ст. 7 115‑ФЗ)", kind: "Шаблон Банка России № 4" });
    d.push({
      path: "/api/v1/documents/5",
      file: "zayavlenie-v-mvk.docx",
      title: "Заявление в МВК об отказе в операции, после первого уровня",
      kind: "Шаблон Банка России № 5",
      needsFirstLevel: true,
    });
  }
  if (scenario === "operation_refusal" || scenario === "contract_refusal")
    d.push({
      path: "/api/v1/documents/team/reminder_13_4",
      file: "napominanie-srok-13-4.docx",
      title: "Напоминание банку: срок п. 13.4 истёк",
      kind: "Шаблон Навигатора, не Банка России",
      note: "Только если семь рабочих дней банка уже прошли: срок посчитает сервер по дате представления документов.",
      needsDocsDate: true,
    });
  d.push({ path: "/api/v1/documents/team/cbr_complaint", file: "obrashchenie-v-bank-rossii.docx", title: "Обращение в Банк России", kind: "Шаблон Навигатора, не Банка России" });
  return d;
}

export default function Zayavlenie() {
  const { state, update, ready } = useCase();
  // Итог по каждому документу: рядом со своей кнопкой.
  const [notes, setNotes] = useState<Record<string, { tone: "ok" | "warn" | "error"; lines: string[] }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [codes, setCodes] = useState<Record<string, string>>({});
  useEffect(() => {
    api.documentCodes().then(setCodes).catch(() => setCodes({}));
  }, []);
  // Коды API пользователю не показываем: только тексты из /api/v1/documents/codes.
  const say = (code: string) => codes[code] ?? "Проверьте даты и реквизиты в документе перед отправкой.";
  const x = state.parse?.extraction;

  // Что подставляется из разбора письма и шага «Сроки»: всё видно в форме и редактируется, скрытых полей нет.
  // Дату отказа из даты операции не берём: это разные события (красная команда, атака 7).
  const suggested = useMemo(() => {
    const v: Record<string, string> = {};
    if (!x) return v;
    const op = x.operations[0];
    if (op?.date) v.po_date = op.date;
    if (op?.amount) v.po_amount = `${op.amount.replace(".", ",")} руб.`;
    if (x.reason.level !== "none" && x.reason.evidence.length) v.bank_reasons = x.reason.evidence.map((e) => e.quote).join("; ");
    if (state.events.bank_review_7wd) v.docs_submitted_date = state.events.bank_review_7wd;
    return v;
  }, [x, state.events.bank_review_7wd]);

  // Подставляем один раз, если поле ещё пустое.
  useEffect(() => {
    const v = { ...state.values };
    let changed = false;
    for (const [k, val] of Object.entries(suggested))
      if (!v[k]) {
        v[k] = val;
        changed = true;
      }
    if (changed) update({ values: v });
  }, [suggested]);

  if (ready && !x) {
    return (
      <div className="page">
        <LineStops here="zayavlenie" enabled={false} />
        <div className="page-head">
          <h1>Заявление</h1>
          <p>Сначала разберите письмо банка: набор документов зависит от меры.</p>
        </div>
        <Link className="btn btn-primary" href="/razbor/">
          Разобрать письмо банка
        </Link>
      </div>
    );
  }
  if (!x) return null;

  const set = (k: string, v: string) => update({ values: { ...state.values, [k]: v } });

  // blank: пустой шаблон, полей формы в запросе нет. Исключение: напоминание о сроке п. 13.4 сервер собирает только
  // по дате представления документов (иначе 422), поэтому для него уходит одна эта дата, без реквизитов.
  const download = async (d: Doc, blank = false) => {
    setBusy(blank ? `${d.path}#blank` : d.path);
    setNotes((n) => ({ ...n, [d.path]: { tone: "ok", lines: [] } }));
    const values: Record<string, string> = {};
    if (!blank) for (const [k, v] of Object.entries(state.values)) if (v && k !== "review_due_date") values[k] = v;
    if (blank && d.needsDocsDate && state.values.docs_submitted_date) values.docs_submitted_date = state.values.docs_submitted_date;
    if (values.refusal_date) values.restriction_date = values.refusal_date;
    const body: DocBody = { values, scenario: x.scenario.value };
    if (!blank) body.first_level_done = state.firstLevel ? true : null;
    try {
      const { blob, leftBlank, warnings, reviewDue } = await api.document(d.path, body);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = blank ? d.file.replace(".docx", "-pustoy.docx") : d.file;
      a.click();
      URL.revokeObjectURL(url);
      const lines: string[] = [];
      if (blank) lines.push(d.needsDocsDate ? "Шаблон скачан. На сервер ушла только дата представления документов." : "Пустой шаблон скачан. Данные формы на сервер не отправлялись.");
      else lines.push(leftBlank.length ? `Документ готов. Незаполненных полей в шаблоне: ${leftBlank.length}, заполните их в документе.` : "Документ готов.");
      if (reviewDue) lines.push(`Последний день срока банка по календарю: ${ruDate(reviewDue)}.`);
      // В пустом шаблоне предупреждения о незаполненных датах ожидаемы, их не показываем.
      if (!blank) for (const w of warnings) lines.push(say(w));
      setNotes((n) => ({ ...n, [d.path]: { tone: !blank && warnings.length ? "warn" : "ok", lines } }));
    } catch (e) {
      const lines: string[] = [];
      if (e instanceof DocError && e.status !== 0 && (e.userMessage || e.code)) {
        lines.push("Документ не собран. " + (e.userMessage ?? say(e.code!)));
        if (e.reviewDue) lines.push(`Последний день срока банка по календарю: ${ruDate(e.reviewDue)}.`);
        if (e.code === "docs_submitted_date_missing") lines.push("Заполните поле «Дата, когда вы представили документы в банк» ниже.");
      } else lines.push("Не удалось собрать документ: сервер не ответил. Попробуйте ещё раз.");
      setNotes((n) => ({ ...n, [d.path]: { tone: "error", lines } }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <LineStops here="zayavlenie" enabled />
      <div className="page-head">
        <h1>Заявление</h1>
        <p>
          В документ попадают только факты вашего дела: реквизиты, даты, номера. Доводы, пояснения и оценку действий банка вы пишете
          сами. Незаполненные поля останутся пустыми.
        </p>
      </div>

      <section aria-labelledby="h-docs">
        <h2 id="h-docs" className="block-title">
          Документы для этой меры
        </h2>
        <ul className="doc-list">
          {docsFor(x.scenario.value).map((d, i) => {
            const locked = Boolean(d.needsFirstLevel && !state.firstLevel);
            return (
              <li key={d.path}>
                <div>
                  <p>
                    <b>{d.title}</b>
                  </p>
                  <p className="kind">{d.kind}</p>
                  {locked && (
                    <p className="kind">
                      Подаётся после первого уровня. Если банк уже рассмотрел ваши документы и не снял ограничение, отметьте это на шаге{" "}
                      <Link href="/marshrut/">«Сроки и маршрут»</Link>.
                    </p>
                  )}
                  {d.note && <p className="kind">{d.note}</p>}
                </div>
                <div className="doc-btns">
                  {/* Первый документ в списке и есть следующий шаг по мере; остальные вторичны. */}
                  {!locked && (
                    <button
                      type="button"
                      className={i === 0 ? "btn btn-primary" : "btn btn-quiet"}
                      onClick={() => void download(d)}
                      disabled={busy !== null}
                      aria-label={busy === d.path ? `Собираем документ: ${d.title}` : `Скачать заполненный DOCX: ${d.title}`}
                    >
                      {busy === d.path ? "Собираем документ" : "Скачать заполненный DOCX"}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-quiet"
                    onClick={() => void download(d, true)}
                    disabled={busy !== null}
                    aria-label={`Скачать пустой шаблон: ${d.title}`}
                  >
                    {busy === `${d.path}#blank` ? "Скачиваем шаблон" : "Скачать пустой шаблон"}
                  </button>
                </div>
                <div className={`doc-note${notes[d.path]?.lines.length ? ` is-${notes[d.path].tone}` : ""}`} role="status" aria-live="polite">
                  {notes[d.path]?.lines.length ? (
                    <>
                      {notes[d.path].tone === "warn" && <p className="doc-note-title">Документ собран, проверьте перед отправкой:</p>}
                      <ul>
                        {notes[d.path].lines.map((l) => (
                          <li key={l}>{l}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="section" aria-labelledby="h-facts">
        <h2 id="h-facts">Факты дела</h2>
        <p className="hint">
          Где ваши данные. Поля формы хранятся только в этой вкладке браузера. Когда вы нажимаете «Скачать заполненный DOCX», они
          один раз уходят на сервер команды, чтобы вписать их в шаблон; сервер не сохраняет их ни в базе, ни в журнале (проверено
          при приёмке интерфейса 26.10). Не хотите отправлять ИНН и номер счёта: нажмите «Скачать пустой шаблон» и заполните документ у
          себя: тогда на сервер не уходит ни одно поле (для напоминания о сроке уходит только дата представления документов, без неё
          сервер не посчитает срок).
        </p>
        <p className="hint">Поля с пометкой «из письма» подставлены из разбора: проверьте их, исправьте или очистите.</p>
        <div className="formgrid">
          {FIELDS.filter((f) => !f.only || f.only.includes(x.scenario.value)).map((f) => {
            const fromLetter = Boolean(suggested[f.key]) && state.values[f.key] === suggested[f.key];
            const id = `f-${f.key}`;
            return (
              <div key={f.key} className={f.type === "long" ? "wide" : undefined}>
                <label htmlFor={id}>
                  {f.label}
                  {fromLetter ? <span className="from-letter"> · {f.key === "docs_submitted_date" ? "из шага «Сроки»" : "из письма"}</span> : null}
                </label>
                {f.type === "long" ? (
                  <textarea id={id} rows={3} value={state.values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
                ) : (
                  <input id={id} type={f.type ?? "text"} value={state.values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <div className="actions">
        <Link className="btn btn-quiet" href="/marshrut/">
          Вернуться к срокам
        </Link>
      </div>
    </div>
  );
}
