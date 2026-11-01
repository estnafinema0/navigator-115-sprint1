import Link from "next/link";

// Линия сценария как маршрут: пройденные остановки зелёные, «вы здесь» оранжевая.
const STOPS = [
  { key: "razbor", href: "/razbor/", label: "Письмо и карточка" },
  { key: "marshrut", href: "/marshrut/", label: "Сроки и маршрут" },
  { key: "zayavlenie", href: "/zayavlenie/", label: "Заявление" },
];

export function LineStops({ here, enabled }: { here: string; enabled: boolean }) {
  const idx = STOPS.findIndex((s) => s.key === here);
  return (
    <ol className="line-stops" aria-label="Шаги разбора">
      {STOPS.map((s, i) => {
        const cls = i < idx ? "done" : i === idx ? "here" : "";
        const inner = (
          <>
            <span className="dot" aria-hidden="true" />
            <span className="stop-name">
              {s.label}
              {i === idx ? <span className="visually-hidden"> (вы здесь)</span> : null}
            </span>
          </>
        );
        return (
          <li key={s.key} className={cls}>
            {enabled || i === 0 ? (
              <Link href={s.href} aria-current={i === idx ? "step" : undefined}>
                {inner}
              </Link>
            ) : (
              <span className="stop" aria-disabled="true">
                {inner}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
