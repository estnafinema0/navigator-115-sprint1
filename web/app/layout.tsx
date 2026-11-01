import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@fontsource/jost/500.css";
import "@fontsource/jost/600.css";
import "@fontsource/jost/700.css";
import "@fontsource/golos-text/400.css";
import "@fontsource/golos-text/500.css";
import "@fontsource/golos-text/600.css";
import "./globals.css";
import { Colophon } from "@/components/Colophon";
import { Masthead } from "@/components/Masthead";
import { CaseProvider } from "@/lib/store";

export const metadata: Metadata = {
  title: "Навигатор-115: разбор письма банка по 115‑ФЗ",
  description:
    "Вставьте текст уведомления или запроса банка: мера, норма, срок и допустимые пути обжалования, у каждого поля цитата из письма.",
  // Значка у сервиса нет (логотип не утверждён, R-23): пустой значок, чтобы браузер не запрашивал /favicon.ico и не писал 404 в консоль.
  icons: { icon: "data:," },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <a className="skip" href="#main">
          Перейти к содержимому
        </a>
        <CaseProvider>
          <Masthead />
          <main id="main">{children}</main>
          <Colophon />
        </CaseProvider>
      </body>
    </html>
  );
}
