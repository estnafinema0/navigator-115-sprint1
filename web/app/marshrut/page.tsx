"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LineStops } from "@/components/LineStops";
import { RouteGroups } from "@/components/RouteGroups";
import { HereSign } from "@/components/Signs";
import { api, type Deadlines, type Routes } from "@/lib/api";
import { EVENT_LABEL, SCENARIO, SCENARIO_NOTE, amountUnit, ruDate } from "@/lib/labels";
import { useCase } from "@/lib/store";

export default function Marshrut() {
  const { state, update, ready } = useCase();
  const [deadlines, setDeadlines] = useState<Deadlines | null>(null);
  const [routes, setRoutes] = useState<Routes | null>(null);
  const [unlocked, setUnlocked] = useState<Routes | null>(null);
  const [phase, setPhase] = useState<"loading" | "error" | "ok">("loading");
  const [attempt, setAttempt] = useState(0);
  const scenario = state.parse?.extraction.scenario.value;

  useEffect(() => {
    if (!scenario) return;
    let alive = true;
    setPhase("loading");
    // Базовый ответ (первый уровень не пройден) задаёт порядок и условия; второй нужен, только если клиент отметил первый уровень.
    Promise.all([api.deadlines(scenario, state.events), api.routes(scenario, false), state.firstLevel ? api.routes(scenario, true) : Promise.resolve(null)])
      .then(([d, r, u]) => {
        if (!alive) return;
        setDeadlines(d);
        setRoutes(r);
        setUnlocked(u);
        setPhase("ok");
      })
      .catch(() => alive && setPhase("error"));
    return () => {
      alive = false;
    };
  }, [scenario, state.events, state.firstLevel, attempt]);

  if (ready && !state.parse) {
    return (
      <div className="page">
        <LineStops here="marshrut" enabled={false} />
        <div className="page-head">
          <h1>Сроки и маршрут</h1>
          <p>Сначала разберите письмо банка: сроки и маршруты зависят от меры.</p>
        </div>
        <Link className="btn btn-primary" href="/razbor/">
          Разобрать письмо банка
        </Link>
      </div>
    );
  }

  const setEvent = (id: string, v: string) => {
    const next = { ...state.events };
    if (v) next[id] = v;
    else delete next[id];
    update({ events: next });
  };
  const clientDeadline = state.parse?.extraction.deadlines.find((d) => d.applies_to === "client_response");

  return (
    <div className="page">
      <LineStops here="marshrut" enabled />
      <div className="page-head">
        <h1>Сроки и маршрут</h1>
        <p>Даты считает код по производственному календарю 2026 и 2027 годов (постановления Правительства № 1466 и № 1187), а не модель.</p>
      </div>

      {scenario && (
        <div className="sign sign-here">
          <HereSign />
          <div>
            <p className="here-label">Вы здесь</p>
            <h2 className="here-title">{SCENARIO[scenario]}</h2>
            <p className="here-sub">{SCENARIO_NOTE[scenario]}</p>
          </div>
        </div>
      )}

      {phase === "loading" && (
        <p role="status" className="loading-text">
          Считаем сроки по календарю.
        </p>
      )}
      {phase === "error" && (
        <div className="error-box" role="alert">
          <p className="error-title">Сервер не ответил</p>
          <p>Сроки и маршруты не загрузились. Даты, которые вы ввели, сохранены.</p>
          <button type="button" className="btn btn-quiet" onClick={() => setAttempt((n) => n + 1)}>
            Загрузить сроки ещё раз
          </button>
        </div>
      )}

      {phase === "ok" && deadlines && (
        <section aria-labelledby="h-timers">
          <h2 id="h-timers" className="block-title">
            Законные сроки
          </h2>
          {!deadlines.statutory_client_deadline && (
            <p className="notice">
              Законного срока ответа на запрос нет: его ставит банк (Методичка ЦБ, с. 15).{" "}
              {clientDeadline ? <>В вашем письме: «{clientDeadline.raw}».</> : "В письме срок не указан, уточните его у банка."}
            </p>
          )}
          {deadlines.timers.length > 0 ? (
            <ul className="timers">
              {deadlines.timers.map((t) => (
                <li key={t.timer_id} className="timer">
                  <div>
                    <h3>{t.title}</h3>
                    <p className="norm">
                      {t.norm}
                      {t.quote ? (
                        <>
                          : <q>{t.quote}</q>
                        </>
                      ) : null}
                    </p>
                    {!t.verified && <p className="norm">Норма сверяется с первоисточником.</p>}
                    <p className={`who${t.who === "client" ? " client" : ""}`}>{t.who === "client" ? "Это ваш срок" : t.who === "bank" ? "Срок банка" : t.who === "mvk" ? "Срок МВК" : "Срок Банка России"}</p>
                  </div>
                  <div>
                    <label htmlFor={`d-${t.timer_id}`} className="field-label">
                      {EVENT_LABEL[t.timer_id] ?? "Дата события"}
                    </label>
                    <input id={`d-${t.timer_id}`} type="date" value={state.events[t.timer_id] ?? ""} onChange={(e) => setEvent(t.timer_id, e.target.value)} />
                  </div>
                  <div aria-live="polite">
                    {t.due ? (
                      <p className="due">
                        {ruDate(t.due)}
                        <small>
                          {amountUnit(t.amount, t.unit)} от {ruDate(t.start)}
                        </small>
                      </p>
                    ) : (
                      <p className="due wait">
                        {amountUnit(t.amount, t.unit)}. Укажите дату, и срок посчитается.
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p>Для этой меры законных таймеров нет.</p>
          )}
        </section>
      )}

      {phase === "ok" && routes && (
        <section className="routes" aria-labelledby="h-routes">
          <h2 id="h-routes">Куда можно обращаться</h2>
          {/* Отметка нужна, только если в ответе API есть маршруты с условием первого уровня. */}
          {(routes.options.some((o) => !o.available) || state.firstLevel) && (
            <label className="check">
              <input type="checkbox" checked={state.firstLevel} onChange={(e) => update({ firstLevel: e.target.checked })} />
              Банк уже рассмотрел мои документы и не снял ограничение
            </label>
          )}
          <RouteGroups base={routes} unlocked={state.firstLevel ? unlocked : null} />
        </section>
      )}

      <div className="actions">
        <Link className="btn btn-primary" href="/zayavlenie/">
          Собрать заявление
        </Link>
        <Link className="btn btn-quiet" href="/razbor/">
          Вернуться к карточке
        </Link>
      </div>
    </div>
  );
}
