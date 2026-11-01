"use client";

// Состояние дела в браузере: текст письма, разбор, даты событий, поля заявления, отметки пакета.
// Хранится в sessionStorage только для удобства (перезагрузка вкладки); на сервере не хранится.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { GuardResult, ParseResult } from "./api";

export type CaseState = {
  text: string;
  sampleId: string | null;
  parse: ParseResult | null;
  guard: GuardResult | null;
  events: Record<string, string>;
  firstLevel: boolean;
  values: Record<string, string>;
  packed: Record<number, boolean>; // отметки чек-листа пакета: только в этом браузере
};

const EMPTY: CaseState = { text: "", sampleId: null, parse: null, guard: null, events: {}, firstLevel: false, values: {}, packed: {} };
const KEY = "navigator115.case.v1";

type Ctx = { state: CaseState; update: (patch: Partial<CaseState>) => void; reset: () => void; ready: boolean };
const CaseCtx = createContext<Ctx | null>(null);

export function CaseProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CaseState>(EMPTY);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) setState({ ...EMPTY, ...JSON.parse(raw) });
    } catch {
      /* хранилище недоступно: работаем без него */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* хранилище недоступно: работаем без него */
    }
  }, [state, ready]);

  const update = useCallback((patch: Partial<CaseState>) => setState((s) => ({ ...s, ...patch })), []);
  const reset = useCallback(() => setState(EMPTY), []);
  return <CaseCtx.Provider value={{ state, update, reset, ready }}>{children}</CaseCtx.Provider>;
}

export function useCase(): Ctx {
  const c = useContext(CaseCtx);
  if (!c) throw new Error("CaseProvider не подключён");
  return c;
}
