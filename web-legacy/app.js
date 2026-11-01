/* Навигатор-115 — веб-демо MVP. Все вычисления на сервере (API): разбор, сроки, маршруты,
   документы, страж. Браузер только показывает результат. */
(function () {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]);
  const ru = (iso) => (iso ? iso.split('-').reverse().join('.') : '—');

  const SCEN = {
    doc_request: 'Запрос документов или пояснений',
    operation_refusal: 'Отказ в совершении операции (п. 11 ст. 7 115-ФЗ)',
    remote_access_restriction: 'Ограничение интернет-банка, карт или отдельных операций',
    contract_termination: 'Расторжение договора банком',
    contract_refusal: 'Отказ в открытии счёта (заключении договора)',
    zsk_high_cbr_only: 'Высокий уровень риска по платформе ЗСК',
    zsk_measures_7_7: 'Меры по п. 5 ст. 7.7 115-ФЗ',
    zsk_medium: 'Средний уровень риска ЗСК',
    suspension_rfm_court: 'Приостановление по решению Росфинмониторинга или суда',
    fz161_transfer_suspension: '161-ФЗ: перевод приостановлен до подтверждения',
    fz161_restriction: '161-ФЗ: ограничение карт или переводов',
    not_aml: 'Ограничение не по 115-ФЗ (налоговая, приставы)',
    other: 'Другое уведомление банка',
    unknown: 'Мера не определена — уточните текст',
  };
  const MEASURE = {
    document_request: 'запрос документов', operation_refusal: 'отказ в операции', operation_suspension: 'приостановление операции',
    operations_limit: 'ограничение операций', remote_access_restriction: 'ограничение ДБО', card_block: 'блокировка карт',
    contract_termination: 'расторжение договора', contract_refusal: 'отказ в договоре', risk_level: 'уровень риска',
    funds_freeze: 'заморозка средств', other: 'иное',
  };
  const DOC = {
    explanation_operations: 'Пояснения по операциям', explanation_business: 'Пояснения о деятельности', source_of_funds: 'Происхождение средств',
    income_certificate: 'Справка о доходах (2-НДФЛ)', tax_return: 'Налоговая декларация', tax_payment_proof: 'Уплата налогов',
    accounting_statements: 'Бухотчётность', bank_statements_other_banks: 'Выписки других банков', bank_statements_own: 'Выписки по счетам',
    operation_supporting_docs: 'Документы, обосновывающие операцию', contracts: 'Договоры', primary_docs: 'Первичка: акты, УПД, накладные',
    payment_orders: 'Платёжные поручения', cash_usage_proof: 'Расходование наличных', staff_docs: 'Штат, численность',
    premises_docs: 'Аренда помещения', photos_premises: 'Фото офиса или склада', marketplace_docs: 'Документы маркетплейса',
    procurement_logistics: 'Закупка и доставка', questionnaire: 'Анкета', beneficiary_info: 'Бенефициары',
    property_sale_proof: 'Продажа имущества', receipts: 'Чеки', kudir: 'КУДиР', advertising_docs: 'Реклама',
    identity_document: 'Документ, удостоверяющий личность', other: 'Иное (см. цитату)',
  };
  const CHANNEL = { chat: 'чат', online_banking_upload: 'интернет-банк', email: 'e-mail', branch_office: 'отделение', phone: 'телефон', post: 'почта', personal_manager: 'менеджер', other: 'иное' };
  const APPEAL = { mvk: 'МВК при Банке России', cbr_complaint: 'жалоба в Банк России', cbr_161_exclusion: 'заявление об исключении из базы Банка России', court: 'суд', bank_rehabilitation: 'реабилитация в банке', bank_review: 'пересмотр в банке', other: 'иное' };
  const LEVEL = { norm: 'норма указана', law_only: 'назван только закон', contract_only: 'только пункт договора', none: 'не указано банком' };
  const EL = {
    E1: ['Вид меры', 'ИН-01-59/98'], E2: ['Закон и норма', 'ИН-01-59/98'], E3: ['Причина', 'ИН-01-59/98'], E4: ['Что сделать для снятия', 'ИН-01-59/98'],
    deadline: ['Срок', 'ИН-03-59/11 · пошаговая инструкция'], E5: ['Порядок обжалования, МВК', 'ИН-01-59/98, ИН-03-59/11'], E6: ['Канал связи', 'ИН-03-59/11'],
  };
  const OK = { yes: 'ok', norm: 'ok', present: 'ok', external: 'ok', law_only: 'partial', contract_only: 'partial', internal_only: 'partial', partial: 'partial', no: 'missing' };
  const CHIP = { ok: '<span class="chip chip--ok">✓ указано</span>', partial: '<span class="chip chip--warn">◐ частично</span>', missing: '<span class="chip chip--bad">✕ нет</span>' };

  const state = { text: '', res: null, guard: null, focus: null, events: {}, firstLevel: false, deadlines: null, routes: null, values: {} };
  let SAMPLES = { samples: [], guard: [] };

  async function api(path, body, method) {
    const r = await fetch(path, { method: method || (body ? 'POST' : 'GET'), headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r;
  }

  /* ---------- подсветка цитат ---------- */
  function highlight(text, spans) {
    const ss = spans.filter((s) => s.end > s.start).sort((a, b) => a.start - b.start || b.end - a.end);
    let out = '', pos = 0;
    for (const s of ss) {
      if (s.start < pos) continue;
      out += esc(text.slice(pos, s.start)) + `<mark class="${s.cls}">${esc(text.slice(s.start, s.end))}</mark>`;
      pos = s.end;
    }
    return out + esc(text.slice(pos));
  }
  function evOf(obj) { return (obj && obj.evidence) || []; }

  /* ---------- 1. старт ---------- */
  function renderSamples() {
    $('#samples').innerHTML = SAMPLES.samples.map((s, i) =>
      `<button type="button" class="sample" data-i="${i}"><b>${esc(s.title)}</b><span>${esc(s.note)}</span></button>`).join('');
    $('#samples').onclick = (e) => {
      const b = e.target.closest('.sample'); if (!b) return;
      document.querySelectorAll('#samples .sample').forEach((x) => x.classList.remove('is-active'));
      b.classList.add('is-active');
      $('#req-text').value = SAMPLES.samples[+b.dataset.i].text;
    };
    $('#guard-samples').innerHTML = SAMPLES.guard.map((s, i) =>
      `<button type="button" class="sample" data-i="${i}"><b>${esc(s.title)}</b><span>${esc(s.note)}</span></button>`).join('');
    $('#guard-samples').onclick = (e) => {
      const b = e.target.closest('.sample'); if (!b) return;
      $('#guard-text').value = SAMPLES.guard[+b.dataset.i].text;
    };
  }

  async function doParse() {
    const text = $('#req-text').value.trim();
    if (!text) { $('#parse-msg').textContent = 'Вставьте текст или выберите пример.'; return; }
    const mode = $('#fast-mode').checked ? 'rules' : 'hybrid';
    $('#btn-parse').disabled = true;
    $('#parse-msg').innerHTML = `<span class="spinner"></span>${mode === 'rules' ? 'Разбираем правилами…' : 'Разбираем: правила + локальная модель (на ноутбуке ~1 мин)…'}`;
    const t0 = performance.now();
    try {
      const [p, g] = await Promise.all([
        api('/api/v1/parse', { text, mode }).then((r) => r.json()),
        api('/api/v1/guard', { text }).then((r) => r.json()),
      ]);
      Object.assign(state, { text, res: p, guard: g, focus: null, events: {}, firstLevel: false, deadlines: null, routes: null, values: {} });
      state.res.meta.wall = ((performance.now() - t0) / 1000).toFixed(1);
      prefillValues();
      location.hash = '#/card';
    } catch (err) {
      $('#parse-msg').textContent = 'Ошибка разбора: ' + err.message;
    } finally {
      $('#btn-parse').disabled = false;
      if (location.hash === '#/card') $('#parse-msg').textContent = '';
    }
  }

  /* ---------- 2. карточка ---------- */
  function fieldRows(x) {
    const rows = [];
    const add = (key, label, html, evs) => rows.push({ key, label, html, evs: evs || [] });
    const sc = x.scenario;
    add('scenario', 'Что это за мера', `<span class="measure">${esc(SCEN[sc.value] || sc.value)}</span>`, evOf(sc));
    if (x.measures.length) add('measures', 'Меры в тексте', x.measures.map((m) => esc(MEASURE[m.type] || m.type)).join(', '), x.measures.flatMap(evOf));
    const lb = x.legal_basis;
    add('legal', 'Основание', lb.items.length ? `<b>${esc(lb.items.map((i) => i.canonical).join('; '))}</b> <span class="small muted">(${LEVEL[lb.level]})</span>` : `<span class="nq">${LEVEL.none}</span>`, lb.items.flatMap(evOf));
    add('reason', 'Причина', x.reason.level === 'none' ? '<span class="nq">не указана банком</span>' : esc(x.reason.text) + ` <span class="small muted">(${x.reason.level === 'specific' ? 'конкретная' : 'общая'})</span>`, evOf(x.reason));
    add('docs', 'Что запросили', x.requested_items.length
      ? `<ol class="doclist">${x.requested_items.map((i) => `<li>${esc(DOC[i.type] || i.type)}${i.format ? ` <span class="chip">${esc(i.format)}</span>` : ''}</li>`).join('')}</ol>`
      : '<span class="nq">перечень не указан банком</span>', x.requested_items.flatMap(evOf));
    if (x.period) add('period', 'Период', esc(x.period.raw), evOf(x.period));
    const cd = x.deadlines.filter((d) => d.applies_to === 'client_response');
    const bd = x.deadlines.filter((d) => d.applies_to === 'bank_review');
    add('deadline', 'Срок ответа', cd.length ? cd.map((d) => `<b>${esc(d.raw)}</b>${d.date ? ` (${ru(d.date)})` : ''}`).join('; ') : '<span class="nq">срок не указан банком</span>',
      cd.flatMap(evOf));
    if (bd.length) add('bankterm', 'Срок рассмотрения банком', bd.map((d) => esc(d.raw)).join('; '), bd.flatMap(evOf));
    add('channel', 'Канал связи', x.response_channels.length ? x.response_channels.map((c) => esc(CHANNEL[c.type] || c.type)).join(', ') : '<span class="nq">не указан</span>', x.response_channels.flatMap(evOf));
    add('next', 'Что делать (по тексту банка)', x.next_steps.stated ? esc(x.next_steps.text) : '<span class="nq">не объяснено</span>', evOf(x.next_steps));
    if (x.consequences.length) add('conseq', 'Если не ответить', x.consequences.map((c) => esc(c.raw)).join('; '), x.consequences.flatMap(evOf));
    const ap = x.appeal;
    add('appeal', 'Обжалование (по тексту банка)', (ap.routes.length ? ap.routes.map((r) => esc(APPEAL[r.type] || r.type)).join(', ') : '<span class="nq">не указано банком</span>')
      + (ap.explicit_denial ? ` <span class="chip chip--bad">«${esc(ap.explicit_denial.value)}»</span>` : ''),
      ap.routes.flatMap(evOf).concat(evOf(ap.explicit_denial)));
    if (x.operations.length) add('ops', 'Операция', x.operations.map((o) => esc(o.raw)).join('; '), x.operations.flatMap(evOf));
    return rows;
  }

  function renderCard() {
    const el = $('#view-card');
    if (!state.res) { el.innerHTML = empty(); return; }
    const x = state.res.extraction, rep = state.res.report, meta = state.res.meta;
    const rows = fieldRows(x);
    const all = rows.flatMap((r) => r.evs.map((e) => ({ ...e, cls: r.key === state.focus ? 'hl-focus' : 'hl-ok' })));
    const focusFirst = all.filter((s) => s.cls === 'hl-focus').concat(all.filter((s) => s.cls !== 'hl-focus'));
    const g = state.guard;
    const checks = Object.entries(EL).map(([k, [label, src]]) => {
      const st = OK[g.elements[k]] || 'missing';
      return `<li>${CHIP[st]}<div><div class="lbl">${esc(label)}</div><div class="src">${esc(src)}</div></div></li>`;
    }).join('');
    const forb = g.forbidden.length ? `<div class="callout callout--bad small"><b>В тексте есть то, что банк раскрывать не должен:</b> ${g.forbidden.map((f) => esc(f.label)).join('; ')}.</div>` : '';
    const inj = meta.injection_detected ? '<div class="callout callout--warn small"><b>В тексте есть инструкции для программы.</b> Мы их не выполняем: текст только разбирается, каждое поле — с цитатой.</div>' : '';
    const fb = meta.fallback ? `<div class="callout callout--warn small">Модель недоступна — разобрано правилами.</div>` : '';
    const how = meta.mode === 'rules' ? 'правила' : `правила + ${esc((meta.model || 'LLM').replace('hf.co/t-tech/', ''))}`;
    el.innerHTML = `
      <div class="view-head"><div>
        <div class="eyebrow">Шаг 2 · карточка запроса</div>
        <h1>${esc(SCEN[x.scenario.value] || x.scenario.value)}</h1>
        <p class="small muted">Разобрано: ${how} · ${esc(meta.wall)} с · полей с цитатой: ${rep.filled_fields}${rep.snapped_quotes.length ? ` · уточнено цитат: ${rep.snapped_quotes.length}` : ''}${rep.dropped_quotes.length ? ` · отброшено неподтверждённых: ${rep.dropped_quotes.length}` : ''}</p>
      </div><span class="chip chip--active">нажмите на поле — увидите цитату</span></div>
      ${fb}${inj}
      <div class="grid-2">
        <div class="card"><div class="kv">${rows.map((r) => `<div class="k">${esc(r.label)}</div><div class="fieldrow${r.key === state.focus ? ' is-active' : ''}" data-key="${r.key}">${r.html}</div>`).join('')}</div></div>
        <div class="stack">
          <div class="card"><h3>Текст банка</h3><div class="src-text">${highlight(state.text, focusFirst)}</div></div>
          <div class="card"><h3>Что банк должен был указать</h3>
            <p class="small muted">По письмам Банка России ИН-01-59/98 и ИН-03-59/11. Проверка правилами.</p>
            <ul class="checks">${checks}</ul></div>
          ${forb}
          ${x.questions_to_user && x.questions_to_user.length ? `<div class="callout callout--info small">${x.questions_to_user.map(esc).join('<br>')}</div>` : ''}
        </div>
      </div>
      ${nav('start', 'route', 'Сроки и маршрут')}`;
    el.querySelectorAll('.fieldrow').forEach((n) => n.addEventListener('click', () => { state.focus = n.dataset.key === state.focus ? null : n.dataset.key; renderCard(); }));
  }

  /* ---------- 3. сроки и маршрут ---------- */
  async function loadRoute() {
    const sc = state.res.extraction.scenario.value;
    const [d, r] = await Promise.all([
      api('/api/v1/deadlines', { scenario: sc, events: state.events }).then((x) => x.json()),
      api(`/api/v1/routes/${encodeURIComponent(sc)}?first_level_done=${state.firstLevel}`).then((x) => x.json()),
    ]);
    state.deadlines = d; state.routes = r;
  }
  const EVENT_LABEL = {
    refusal_notice_5wd: 'Дата решения банка об отказе', bank_review_7wd: 'Дата, когда вы представили документы',
    cbr_review_15wd: 'Дата подачи заявления в Банк России', cbr_161_review_15wd: 'Дата подачи заявления в Банк России',
    mvk_review_20wd: 'Дата подачи заявления в МВК', mvk_7_7_window_6m: 'Дата получения уведомления о мерах',
    termination_60d: 'Дата уведомления о расторжении', fz161_confirm_next_day: 'Дата приостановления перевода', fz161_suspension_2d: 'Дата приостановления перевода',
  };
  async function renderRoute() {
    const el = $('#view-route');
    if (!state.res) { el.innerHTML = empty(); return; }
    if (!state.deadlines) { el.innerHTML = '<div class="card"><span class="spinner"></span>Считаем сроки по производственному календарю…</div>'; await loadRoute(); }
    const d = state.deadlines, r = state.routes, x = state.res.extraction;
    const cd = x.deadlines.find((t) => t.applies_to === 'client_response');
    const noLegal = !d.statutory_client_deadline
      ? `<div class="callout callout--info small"><b>Законного срока ответа на запрос нет — срок ставит банк.</b> ${cd ? `В вашем тексте: «${esc(cd.raw)}».` : 'В тексте срок не указан — уточните у банка.'}</div>` : '';
    const timers = d.timers.length ? `<table class="tbl"><tr><th>Срок</th><th>С какой даты</th><th>Истекает</th><th>Норма</th></tr>${d.timers.map((t) => `
      <tr><td>${esc(t.title || '')}${t.who === 'client' ? ' <span class="chip chip--warn">ваш срок</span>' : ''}</td>
      <td><input type="date" data-timer="${t.timer_id}" value="${esc(state.events[t.timer_id] || '')}" aria-label="${esc(EVENT_LABEL[t.timer_id] || 'дата')}"><div class="small muted">${esc(EVENT_LABEL[t.timer_id] || '')}</div></td>
      <td>${t.due ? `<b>${ru(t.due)}</b><div class="small muted">${t.amount} ${t.unit === 'working_days' ? 'р. д.' : t.unit === 'months' ? 'мес.' : 'дн.'}</div>` : `<span class="muted">${esc(t.status || '')}</span>`}</td>
      <td class="small">${esc(t.norm || '')}${t.verified === false ? ' <span class="chip chip--warn">сверяется</span>' : ''}</td></tr>`).join('')}</table>`
      : '<p class="muted">Для этой меры законных таймеров нет.</p>';
    const routes = r.options.map((o) => `<div class="route${o.available ? '' : ' is-blocked'}"><b>${esc(o.title)}</b>
      ${o.template ? ` <span class="chip">шаблон Банка России № ${o.template}</span>` : ''}${o.deadline_months ? ` <span class="chip chip--warn">в течение ${o.deadline_months} мес.</span>` : ''}
      ${o.norm ? `<div class="small muted">${esc(o.norm)}</div>` : ''}${o.available ? '' : `<div class="small">⏸ ${esc(o.blocked_reason)}</div>`}</div>`).join('');
    el.innerHTML = `
      <div class="view-head"><div><div class="eyebrow">Шаг 3 · сроки и маршрут</div>
        <h1>${esc(SCEN[x.scenario.value] || '')}</h1>
        <p class="small muted">Даты считает код по производственному календарю 2026–2027 (постановления Правительства № 1466 и № 1187), не модель.</p></div></div>
      ${noLegal}
      <div class="grid-2">
        <div class="card"><h3>Законные сроки</h3>${timers}</div>
        <div class="stack">
          <div class="card"><h3>Куда можно обращаться</h3>
            <label class="small"><input type="checkbox" id="first-level" ${state.firstLevel ? 'checked' : ''}> Банк уже рассмотрел мои документы и не снял ограничение (первый уровень пройден)</label>
            <div style="margin-top:10px">${routes}</div></div>
          ${r.mvk_note ? `<div class="callout callout--warn small"><b>МВК для вашего случая недопустима.</b> ${esc(r.mvk_note)}</div>` : ''}
        </div>
      </div>
      ${nav('card', 'docs', 'Заявление')}`;
    el.querySelectorAll('input[data-timer]').forEach((inp) => inp.addEventListener('change', async () => {
      if (inp.value) state.events[inp.dataset.timer] = inp.value; else delete state.events[inp.dataset.timer];
      state.deadlines = null; await renderRoute();
    }));
    $('#first-level').addEventListener('change', async (e) => { state.firstLevel = e.target.checked; state.deadlines = null; await renderRoute(); });
  }

  /* ---------- 4. заявление ---------- */
  const FORM = [
    ['company_name', 'Заявитель (наименование / ФИО ИП)'], ['company_inn', 'ИНН'], ['company_address', 'Адрес'], ['company_phone', 'Телефон'],
    ['bank_full_name', 'Банк (полное наименование)'], ['contract_number', 'Договор счёта №'], ['contract_date', 'Дата договора'],
    ['refusal_date', 'Дата отказа / ограничения'], ['po_date', 'Платёжка: дата'], ['po_number', 'Платёжка: №'], ['po_amount', 'Платёжка: сумма'],
    ['po_purpose', 'Платёжка: назначение'], ['reasons_letter_date', 'Письмо банка о причинах: дата'], ['reasons_letter_number', 'Письмо банка: №'],
    ['docs_submitted_date', 'Дата представления документов'], ['attachments', 'Приложения (перечень)'],
  ];
  function prefillValues() {
    const x = state.res.extraction, v = state.values;
    const op = x.operations[0];
    if (op && op.date) { v.refusal_date = op.date; v.po_date = op.date; }
    if (op && op.amount) v.po_amount = op.amount.replace('.', ',') + ' руб.';
    if (x.reason.level !== 'none' && x.reason.evidence.length) v.bank_reasons = x.reason.evidence.map((e) => e.quote).join('; ');
  }
  function renderDocs() {
    const el = $('#view-docs');
    if (!state.res) { el.innerHTML = empty(); return; }
    const sc = state.res.extraction.scenario.value;
    const tpl = [];
    if (sc === 'remote_access_restriction') tpl.push([1, 'Запрос причин ограничения ДБО (шаблон Банка России № 1)']);
    if (sc === 'operation_refusal') tpl.push([4, 'Документы после отказа, п. 13.4 (шаблон Банка России № 4)'], [5, 'Заявление в МВК (шаблон Банка России № 5) — после первого уровня']);
    const team = [];
    if (sc === 'operation_refusal' || sc === 'contract_refusal') team.push(['reminder_13_4', 'Напоминание: срок п. 13.4 истёк (шаблон Навигатора)']);
    team.push(['cbr_complaint', 'Обращение в Банк России (шаблон Навигатора)']);
    const v = state.values;
    el.innerHTML = `
      <div class="view-head"><div><div class="eyebrow">Шаг 4 · заявление</div><h1>Документ по шаблону</h1>
        <p class="small muted">Заполняются только факты вашего дела. Доводы, пояснения и оценку действий банка пишете вы сами. Пустые поля остаются пустыми.</p></div></div>
      <div class="grid-2">
        <div class="card"><h3>Данные дела</h3><div class="formgrid">${FORM.map(([k, l]) =>
          `<div><label for="f-${k}">${esc(l)}</label><input id="f-${k}" data-k="${k}" ${/date/.test(k) ? 'type="date"' : ''} value="${esc(v[k] || '')}"></div>`).join('')}</div>
          <p class="small muted" style="margin-top:8px">Данные остаются в этом окне и уходят только на сервер команды для заполнения шаблона. Не храним.</p></div>
        <div class="stack"><div class="card"><h3>Скачать</h3>
          ${tpl.map(([n, t]) => `<button class="btn btn--primary" style="margin:4px 0" data-tpl="${n}">${esc(t)}</button>`).join('<br>') || '<p class="muted small">Для этой меры шаблона Банка России в MVP нет.</p>'}
          <br>${team.map(([n, t]) => `<button class="btn" style="margin:4px 0" data-team="${n}">${esc(t)}</button>`).join('<br>')}
          <p class="small" id="doc-msg" role="status"></p></div></div>
      </div>
      ${nav('route', null, null)}`;
    el.querySelectorAll('input[data-k]').forEach((i) => i.addEventListener('input', () => { state.values[i.dataset.k] = i.value; }));
    el.querySelectorAll('[data-tpl]').forEach((b) => b.addEventListener('click', () => download(`/api/v1/documents/${b.dataset.tpl}`, `cbr-template-${b.dataset.tpl}.docx`)));
    el.querySelectorAll('[data-team]').forEach((b) => b.addEventListener('click', () => download(`/api/v1/documents/team/${b.dataset.team}`, `navigator-${b.dataset.team}.docx`)));
  }
  async function download(path, name) {
    const values = Object.fromEntries(Object.entries(state.values).filter(([, x]) => x));
    try {
      const r = await api(path, { values });
      const blank = r.headers.get('X-Fields-Left-Blank');
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name; a.click();
      $('#doc-msg').textContent = blank ? `Готово. Остались пустыми: ${blank.split(',').length} полей — заполните их в документе.` : 'Готово.';
    } catch (e) { $('#doc-msg').textContent = 'Ошибка: ' + e.message; }
  }

  /* ---------- страж ---------- */
  async function runGuard() {
    const text = $('#guard-text').value.trim(); if (!text) return;
    const g = await api('/api/v1/guard', { text }).then((r) => r.json());
    const checks = Object.entries(EL).map(([k, [label, src]]) => `<li>${CHIP[OK[g.elements[k]] || 'missing']}<div><div class="lbl">${esc(label)}</div><div class="src">${esc(src)}</div></div></li>`).join('');
    const forb = g.forbidden.map((f) => `<li><span class="chip chip--bad">запрещено</span><div><div class="lbl">${esc(f.label)}</div><div class="src">${esc(f.basis)}</div><div class="det">«${esc(f.hits[0].quote)}»</div></div></li>`).join('');
    const verdict = { red: 'Нельзя отправлять: есть запрещённое', yellow: 'Неполное: не хватает обязательных элементов', green: 'Все обязательные элементы на месте' }[g.light];
    $('#guard-result').innerHTML = `<div class="light" data-v="${g.light}"><i></i><i></i><i></i></div><h3 style="margin-top:10px">${esc(verdict)}</h3>
      <ul class="checks">${forb}${checks}</ul>`;
    const spans = Object.values(g.evidence).flat().map((h) => ({ ...h, cls: 'hl-ok' }))
      .concat(g.forbidden.flatMap((f) => f.hits.map((h) => ({ ...h, cls: 'hl-bad' }))));
    $('#guard-marked').innerHTML = highlight(text, spans.sort((a, b) => (a.cls === 'hl-bad' ? -1 : 1)));
    $('#guard-marked-card').classList.remove('hidden');
  }

  /* ---------- навигация ---------- */
  function empty() { return `<div class="card empty"><p>Сначала вставьте текст запроса на шаге 1.</p><a class="btn btn--primary" href="#/start">К шагу 1</a></div>`; }
  function nav(prev, next, label) {
    return `<div class="actions actions--split" style="margin-top:16px">${prev ? `<a class="btn" href="#/${prev}">← Назад</a>` : '<span></span>'}${next ? `<a class="btn btn--primary" href="#/${next}">${esc(label)} →</a>` : ''}</div>`;
  }
  const VIEWS = ['start', 'card', 'route', 'docs', 'guard'];
  async function route() {
    const v = (location.hash.replace('#/', '') || 'start');
    const view = VIEWS.includes(v) ? v : 'start';
    VIEWS.forEach((x) => { const s = $('#view-' + x); if (s) s.classList.toggle('hidden', x !== view); });
    document.querySelectorAll('#stepper a').forEach((a) => a.classList.toggle('is-active', a.dataset.step === view));
    $('#stepper').classList.toggle('hidden', view === 'guard');
    document.querySelectorAll('.mode').forEach((m) => m.classList.toggle('is-active', (m.dataset.mode === 'bank') === (view === 'guard')));
    if (view === 'card') renderCard();
    if (view === 'route') await renderRoute();
    if (view === 'docs') renderDocs();
    window.scrollTo(0, 0);
  }

  async function init() {
    try { SAMPLES = await fetch('samples.json').then((r) => r.json()); } catch (e) { /* без примеров */ }
    renderSamples();
    $('#btn-parse').addEventListener('click', doParse);
    $('#btn-guard').addEventListener('click', runGuard);
    window.addEventListener('hashchange', route);
    route();
  }
  init();
})();
