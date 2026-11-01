// Подписи для интерфейса. Источник норм в пояснениях указан явно.

export const SCENARIO: Record<string, string> = {
  doc_request: "Запрос документов или пояснений",
  operation_refusal: "Отказ в совершении операции",
  remote_access_restriction: "Ограничение интернет-банка, карт или отдельных операций",
  contract_termination: "Расторжение договора банком",
  contract_refusal: "Отказ в открытии счёта",
  zsk_high_cbr_only: "Высокий уровень риска на платформе ЗСК",
  zsk_measures_7_7: "Меры по п. 5 ст. 7.7 115‑ФЗ",
  zsk_medium: "Средний уровень риска ЗСК",
  suspension_rfm_court: "Приостановление по решению Росфинмониторинга или суда",
  fz161_transfer_suspension: "161‑ФЗ: перевод приостановлен до подтверждения",
  fz161_restriction: "161‑ФЗ: ограничение карт или переводов",
  not_aml: "Ограничение не по 115‑ФЗ: налоговая, приставы",
  other: "Другое уведомление банка",
  unknown: "Мера не определена",
};

// Подпись под «Вы здесь»: что это значит для маршрута (Методичка ЦБ, с. 15, 16, 18).
export const SCENARIO_NOTE: Record<string, string> = {
  doc_request: "Это ещё не решение банка. Законного срока ответа нет: его ставит банк по договору и своим правилам (Методичка ЦБ, с. 15).",
  operation_refusal: "Одно из четырёх решений, которые рассматривает МВК, но только после первого уровня: сначала банк рассматривает ваши документы (п. 13.4 ст. 7 115‑ФЗ).",
  remote_access_restriction: "Мера банка по договору и внутренним правилам. Это не отказ в операции и не одно из четырёх решений, которые рассматривает МВК (Методичка ЦБ, с. 16, 18).",
  contract_termination: "Расторжение не входит в четыре вида решений, которые рассматривает МВК.",
  contract_refusal: "Одно из четырёх решений, которые рассматривает МВК, после первого уровня в банке.",
  zsk_high_cbr_only: "Сначала заявление в Банк России о пересмотре уровня риска, затем МВК.",
  zsk_measures_7_7: "МВК рассматривает эти меры. На заявление есть шесть месяцев (ст. 7.8 115‑ФЗ).",
  zsk_medium: "Средний уровень риска не входит в четыре вида решений, которые рассматривает МВК.",
  suspension_rfm_court: "Такое приостановление не входит в четыре вида решений МВК. Нужен юрист.",
  fz161_transfer_suspension: "Меры по 161‑ФЗ МВК не рассматривает. Перевод подтверждают в банке.",
  fz161_restriction: "Меры по 161‑ФЗ МВК не рассматривает. Путь: заявление об исключении сведений из базы Банка России.",
  not_aml: "Это не 115‑ФЗ: снимать ограничение нужно там, где его наложили.",
  other: "По тексту мера не названа. Уточните у банка, что именно произошло.",
  unknown: "Не удалось определить меру по тексту. Проверьте, что скопировано всё сообщение банка.",
};

export const MEASURE: Record<string, string> = {
  document_request: "запрос документов",
  operation_refusal: "отказ в операции",
  operation_suspension: "приостановление операции",
  operations_limit: "ограничение операций",
  remote_access_restriction: "ограничение интернет-банка",
  card_block: "блокировка карт",
  contract_termination: "расторжение договора",
  contract_refusal: "отказ в договоре",
  risk_level: "уровень риска",
  funds_freeze: "заморозка средств",
  other: "иное",
};

export const DOC: Record<string, string> = {
  explanation_operations: "Пояснения по операциям",
  explanation_business: "Пояснения о деятельности",
  source_of_funds: "Происхождение средств",
  income_certificate: "Справка о доходах (2-НДФЛ)",
  tax_return: "Налоговая декларация",
  tax_payment_proof: "Подтверждение уплаты налогов",
  accounting_statements: "Бухгалтерская отчётность",
  bank_statements_other_banks: "Выписки из других банков",
  bank_statements_own: "Выписки по счетам",
  operation_supporting_docs: "Документы, обосновывающие операцию",
  contracts: "Договоры",
  primary_docs: "Акты, УПД, накладные",
  payment_orders: "Платёжные поручения",
  cash_usage_proof: "Расходование наличных",
  staff_docs: "Штат и численность",
  premises_docs: "Аренда помещения",
  photos_premises: "Фото офиса или склада",
  marketplace_docs: "Документы маркетплейса",
  procurement_logistics: "Закупка и доставка",
  questionnaire: "Анкета",
  beneficiary_info: "Бенефициары",
  property_sale_proof: "Продажа имущества",
  receipts: "Чеки",
  kudir: "КУДиР",
  advertising_docs: "Реклама",
  identity_document: "Документ, удостоверяющий личность",
  other: "Иное (см. цитату)",
};

export const CHANNEL: Record<string, string> = {
  chat: "чат банка",
  online_banking_upload: "интернет-банк",
  email: "электронная почта",
  branch_office: "отделение",
  phone: "телефон",
  post: "почта",
  personal_manager: "менеджер",
  other: "иное",
};

export const APPEAL: Record<string, string> = {
  mvk: "МВК при Банке России",
  cbr_complaint: "жалоба в Банк России",
  cbr_161_exclusion: "исключение из базы Банка России",
  court: "суд",
  bank_rehabilitation: "реабилитация в самом банке",
  bank_review: "пересмотр в самом банке",
  other: "иное",
};

export const LEGAL_LEVEL: Record<string, string> = {
  norm: "норма указана",
  law_only: "назван только закон",
  contract_only: "только пункт договора",
  none: "не указано",
};

// Что банк обязан сообщить (письма Банка России ИН-01-59/98 и ИН-03-59/11).
export const ELEMENTS: { key: string; label: string; src: string }[] = [
  { key: "E1", label: "Вид меры", src: "ИН-01-59/98" },
  { key: "E2", label: "Закон и конкретная норма", src: "ИН-01-59/98" },
  { key: "E3", label: "Причина", src: "ИН-01-59/98" },
  { key: "E4", label: "Что сделать, чтобы снять меру", src: "ИН-01-59/98" },
  { key: "deadline", label: "Срок", src: "ИН-03-59/11, пошаговая инструкция" },
  { key: "E5", label: "Порядок обжалования, включая МВК", src: "ИН-01-59/98, ИН-03-59/11" },
  { key: "E6", label: "Канал связи с банком", src: "ИН-03-59/11" },
];
export const ELEMENT_OK = new Set(["yes", "norm", "present", "external"]);
export const ELEMENT_PARTIAL = new Set(["law_only", "contract_only", "internal_only", "partial"]);

export const EVENT_LABEL: Record<string, string> = {
  refusal_notice_5wd: "Дата решения банка",
  bank_review_7wd: "Дата, когда вы представили документы",
  cbr_review_15wd: "Дата подачи заявления в Банк России",
  cbr_161_review_15wd: "Дата подачи заявления в Банк России",
  mvk_review_20wd: "Дата подачи заявления в МВК",
  mvk_7_7_window_6m: "Дата получения уведомления о мерах",
  termination_60d: "Дата уведомления о расторжении",
  fz161_confirm_next_day: "Дата приостановления перевода",
  fz161_suspension_2d: "Дата приостановления перевода",
};

export const UNIT: Record<string, string> = { working_days: "р. д.", calendar_days: "дн.", months: "мес." };

const UNIT_FORMS: Record<string, [string, string, string]> = {
  working_days: ["рабочий день", "рабочих дня", "рабочих дней"],
  calendar_days: ["календарный день", "календарных дня", "календарных дней"],
  months: ["месяц", "месяца", "месяцев"],
};

/** «5 рабочих дней», «3 рабочих дня», «1 рабочий день». */
export function amountUnit(n: number, unit: string): string {
  const f = UNIT_FORMS[unit];
  if (!f) return `${n} ${UNIT[unit] ?? ""}`.trim();
  const a = Math.abs(n) % 100, b = a % 10;
  const w = a > 10 && a < 20 ? f[2] : b === 1 ? f[0] : b >= 2 && b <= 4 ? f[1] : f[2];
  return `${n} ${w}`;
}

export function ruDate(iso?: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}
