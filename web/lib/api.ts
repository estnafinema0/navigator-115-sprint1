// Вызовы API Навигатора-115 (FastAPI, тот же origin). Все вычисления на сервере команды.

export type Evidence = { quote: string; start?: number; end?: number };
type WithEv = { evidence: Evidence[] };

export type Extraction = {
  scenario: { value: string; confidence: number } & WithEv;
  measures: ({ type: string } & WithEv)[];
  legal_basis: { level: string; items: ({ canonical: string; kind: string } & WithEv)[] };
  reason: { level: string; text: string | null } & WithEv;
  requested_items: ({ type: string; raw: string; format?: string | null } & WithEv)[];
  period: ({ raw: string } & WithEv) | null;
  deadlines: ({ applies_to: string; kind: string; date?: string | null; raw: string } & WithEv)[];
  response_channels: ({ type: string; raw: string } & WithEv)[];
  next_steps: { stated: boolean; text: string | null } & WithEv;
  consequences: ({ type: string; raw: string } & WithEv)[];
  appeal: { level: string; routes: ({ type: string } & WithEv)[]; explicit_denial: ({ value: string } & WithEv) | null };
  operations: ({ date?: string | null; amount?: string | null; raw: string } & WithEv)[];
  questions_to_user?: string[];
};

export type ParseResult = {
  extraction: Extraction;
  report: { filled_fields: number; snapped_quotes: string[]; dropped_quotes: string[]; dropped_fields: string[] };
  meta: { mode: string; model?: string; seconds?: number; fallback?: string; injection_detected?: boolean };
  disclaimer: string;
};

export type Hit = { start: number; end: number; quote: string };
export type GuardResult = {
  elements: Record<string, string>;
  evidence: Record<string, Hit[]>;
  forbidden: { id: string; label: string; basis: string; hits: Hit[] }[];
  // Не запрещено само по себе, но решение за комплаенсом банка (жёлтый свет без недостающих элементов).
  review?: { id: string; label: string; basis: string; hits: Hit[] }[];
  light: "green" | "yellow" | "red";
};

export type RouteOption = {
  id: string;
  title: string;
  available: boolean;
  blocked_reason: string | null;
  norm: string | null;
  template: number | null;
  deadline_months: number | null;
};
export type Routes = { scenario: string; mvk_note: string | null; options: RouteOption[] };

export type Timer = {
  timer_id: string;
  title: string;
  norm: string;
  who: string;
  verified: boolean;
  amount: number;
  unit: string;
  quote?: string | null;
  start?: string;
  due?: string;
  status?: string;
};
export type PackageItem = { index: number; type: string; raw: string; files: string[]; status: string };
export type PackageResult = {
  items: PackageItem[];
  completeness: { done: number; total: number; pct: number | null };
  followups: { text: string; source: string; label: string }[];
  pdn_note: string;
  disclaimer: string;
};

export type Deadlines = { scenario: string; statutory_client_deadline: boolean; timers: Timer[] };

export type DocBody = { values: Record<string, string>; scenario?: string; first_level_done?: boolean | null };
export type DocResult = { blob: Blob; leftBlank: string[]; warnings: string[]; reviewDue: string | null };
export class DocError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    public userMessage: string | null,
    public reviewDue: string | null = null,
  ) {
    super(code ?? `status ${status}`);
  }
}

async function call(path: string, body?: unknown): Promise<Response> {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Сервер ответил ${r.status}`);
  return r;
}

export const api = {
  parse: (text: string, mode: "rules" | "hybrid") => call("/api/v1/parse", { text, mode }).then((r) => r.json() as Promise<ParseResult>),
  guard: (text: string) => call("/api/v1/guard", { text }).then((r) => r.json() as Promise<GuardResult>),
  routes: (scenario: string, firstLevel: boolean) =>
    call(`/api/v1/routes/${encodeURIComponent(scenario)}?first_level_done=${firstLevel}`).then((r) => r.json() as Promise<Routes>),
  deadlines: (scenario: string, events: Record<string, string>) =>
    call("/api/v1/deadlines", { scenario, events }).then((r) => r.json() as Promise<Deadlines>),
  // Чек-лист пакета (M3): отправляем только разбор, файлы и отметки остаются в браузере.
  package: (extraction: Extraction) => call("/api/v1/package", { extraction, files: [] }).then((r) => r.json() as Promise<PackageResult>),
  // Документы: 200 с предупреждениями в заголовке или 409/422 с причиной отказа (detail.code, detail.message).
  document: async (path: string, body: DocBody): Promise<DocResult> => {
    let r: Response;
    try {
      r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      throw new DocError(0, null, null);
    }
    if (r.status === 409 || r.status === 422) {
      const j = await r.json().catch(() => null);
      const d = j?.detail && typeof j.detail === "object" ? j.detail : null;
      throw new DocError(r.status, d?.code ?? null, d?.message ?? null, d?.review_due_date ?? null);
    }
    if (!r.ok) throw new DocError(r.status, null, null);
    const list = (h: string) => (r.headers.get(h) || "").split(",").map((x) => x.trim()).filter(Boolean);
    return {
      blob: await r.blob(),
      leftBlank: list("X-Fields-Left-Blank"),
      warnings: list("X-Navigator-Warnings"),
      reviewDue: r.headers.get("X-Review-Due-Date"),
    };
  },
  documentCodes: () => call("/api/v1/documents/codes").then((r) => r.json() as Promise<Record<string, string>>),
};
