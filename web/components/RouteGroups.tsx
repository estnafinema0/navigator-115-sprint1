import type { AnimationEvent } from "react";
import type { RouteOption, Routes } from "@/lib/api";
import { amountUnit } from "@/lib/labels";
import { ArrowSign, BarSign } from "./Signs";

// Маршруты из /api/v1/routes разложены на группы только по данным ответа:
// порядок маршрутов в ответе (первый доступный = основной шаг) и условие available/blocked_reason
// (маршрут откроется после первого уровня). Своей юридической логики здесь нет.

export type RoutePlan = { now: RouteOption | null; ifNot: RouteOption[]; also: RouteOption[] };

/** base: ответ при first_level_done=false; unlocked: ответ при first_level_done=true (если клиент отметил первый уровень). */
export function planRoutes(base: Routes, unlocked?: Routes | null): RoutePlan {
  const conditional = base.options.filter((o) => !o.available).map((o) => o.id);
  if (unlocked) {
    const opened = unlocked.options.filter((o) => o.available && conditional.includes(o.id));
    const now = opened[0] ?? unlocked.options.find((o) => o.available) ?? null;
    return {
      now,
      ifNot: unlocked.options.filter((o) => !o.available),
      also: unlocked.options.filter((o) => o.available && o.id !== now?.id),
    };
  }
  const now = base.options.find((o) => o.available) ?? null;
  return {
    now,
    ifNot: base.options.filter((o) => !o.available),
    also: base.options.filter((o) => o.available && o.id !== now?.id),
  };
}

function Source({ o }: { o: RouteOption }) {
  const parts = [o.norm, o.template ? `шаблон Банка России № ${o.template}` : null].filter(Boolean);
  return parts.length ? <p className="route-src">{parts.join(" · ")}</p> : null;
}

type Props = { base: Routes; unlocked?: Routes | null; rise?: boolean; onRiseEnd?: () => void; mvkTail?: string };

export function RouteGroups({ base, unlocked, rise, onRiseEnd, mvkTail }: Props) {
  const plan = planRoutes(base, unlocked);
  let n = 0;
  // Шаг появления 80 мс (DESIGN.md, разд. 6); перечёркнутый щит последним.
  const delay = () => ({ animationDelay: `${60 + 80 * n++}ms` });
  const total = (plan.now ? 1 : 0) + plan.ifNot.length + plan.also.length + (base.mvk_note ? 1 : 0);
  // Класс появления снимается, когда доиграл последний щит, а не первый.
  const onEnd = (e: AnimationEvent<HTMLDivElement>) => {
    const li = (e.target as HTMLElement).closest("li");
    const all = e.currentTarget.querySelectorAll(".route-list > li");
    if (li && all.length === total && li === all[all.length - 1]) onRiseEnd?.();
  };
  return (
    <div className={`route-groups${rise ? " rise" : ""}`} onAnimationEnd={onEnd}>
      {plan.now && (
        <div className="route-group">
          <h3 className="group-title">Сейчас</h3>
          <ol className="route-list route-list-now">
            <li className="sign" style={delay()}>
              <ArrowSign />
              <div>
                <p className="rt">{plan.now.title}</p>
                {plan.now.deadline_months ? <p>Подать в течение {amountUnit(plan.now.deadline_months, "months")}.</p> : null}
                <Source o={plan.now} />
              </div>
            </li>
          </ol>
        </div>
      )}
      {plan.ifNot.length > 0 && (
        <div className="route-group">
          <h3 className="group-title">Если не помогло</h3>
          <ol className="route-list">
            {plan.ifNot.map((o) => (
              <li key={o.id} className="sign sign-wait" style={delay()}>
                <ArrowSign />
                <div>
                  <p className="rt">{o.title}</p>
                  <p>
                    {o.blocked_reason ? `${o.blocked_reason}.` : ""}
                    {o.deadline_months ? ` Подать в течение ${amountUnit(o.deadline_months, "months")}.` : ""}
                  </p>
                  <Source o={o} />
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {plan.also.length > 0 && (
        <div className="route-group">
          <h3 className="group-title">Также доступно</h3>
          <ol className="route-list">
            {plan.also.map((o) => (
              <li key={o.id} className="route-alt" style={delay()}>
                <ArrowSign />
                <div>
                  <p className="rt">{o.title}</p>
                  {o.deadline_months ? <p>Подать в течение {amountUnit(o.deadline_months, "months")}.</p> : null}
                  <Source o={o} />
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {base.mvk_note && (
        <div className="route-group">
          <h3 className="group-title">Нельзя</h3>
          <ol className="route-list">
            <li className="sign sign-no" style={delay()}>
              <BarSign />
              <div>
                <p className="rt">МВК при Банке России: недопустима</p>
                <p>
                  {base.mvk_note}
                  {mvkTail ? ` ${mvkTail}` : ""}
                </p>
              </div>
            </li>
          </ol>
        </div>
      )}
    </div>
  );
}
