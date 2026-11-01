"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/razbor/", label: "Разобрать письмо" },
  { href: "/strazh/", label: "Страж для банка" },
  { href: "/#granica", label: "Границы сервиса" },
];

export function Masthead() {
  const path = usePathname();
  return (
    <header className="masthead">
      <Link className="wordmark" href="/">
        Навигатор&#8209;115
      </Link>
      <nav aria-label="Разделы">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} aria-current={path === n.href ? "page" : undefined}>
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
