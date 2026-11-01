// Три собственных знака (DESIGN.md, разд. 4): штрих 2,4 px, квадратные концы.
// Стрелка: направление маршрута. Круг с диагональю: запрет. Треугольник: «вы здесь».

type P = { className?: string; title?: string };

export function ArrowSign({ className = "ic" }: P) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M3 12h16M13 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square" strokeLinejoin="miter" />
    </svg>
  );
}

export function BarSign({ className = "ic" }: P) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <path d="M5.6 5.6l12.8 12.8" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square" />
    </svg>
  );
}

export function HereSign({ className = "ic ic-here" }: P) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3l9 18H3z" fill="currentColor" />
    </svg>
  );
}
