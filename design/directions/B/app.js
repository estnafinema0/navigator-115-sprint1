/* Направление B: состояния, табель рабочих дней, связь «строка таблицы ↔ цитата», копирование.
   Бэкенда нет: разбор примера подготовлен заранее по корпусу Pulsar (пример 1).
   Расчёт сроков детерминированный: календарь 2026 года зашит ниже, сверить перед релизом. */
(function () {
  'use strict';

  var EXAMPLE_TEXT =
    '«…по причине сомнительного характера операций действие услуги Сбербанк Онлайн/банковских карт заблокировано. Для получения денежных средств… обращаться в офис банка с документом, удостоверяющим личность».\n«…по причине подозрения в легализации (отмывании) доходов, полученных преступным путем, Вам отказано в совершении операции на …RUB от 25.03.2024 на основании п.11 ст.7 № 115-ФЗ. Если Вы не согласны с отказом, оформите в офисе заявление на реабилитацию с обосновывающими операцию документами/пояснениями.»';

  /* Праздничные и перенесённые выходные 2026 года (постановление Правительства о переносе выходных; сверить) */
  var HOLIDAYS_2026 = ['01-01','01-02','01-03','01-04','01-05','01-06','01-07','01-08','01-09','02-23','03-09','05-01','05-11','06-12','11-04','12-31'];
  var WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

  function key(d) { return (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate(); }
  function isOff(d) { var w = d.getDay(); return w === 0 || w === 6 || (d.getFullYear() === 2026 && HOLIDAYS_2026.indexOf(key(d)) !== -1); }
  function fmt(d) { return (d.getDate() < 10 ? '0' : '') + d.getDate() + '.' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '.' + d.getFullYear(); }
  function addDays(d, n) { var r = new Date(d); r.setDate(r.getDate() + n); return r; }
  function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }

  /* N-й рабочий день после даты (отсчёт со следующего дня) */
  function workingDay(from, n) {
    var d = new Date(from), count = 0;
    while (count < n) { d = addDays(d, 1); if (!isOff(d)) count++; }
    return d;
  }

  var strip = document.getElementById('strip');
  var summary = document.getElementById('board-summary');
  var dateInput = document.getElementById('submit-date');

  function renderStrip() {
    var parts = dateInput.value.split('-');
    if (parts.length !== 3) return;
    var submit = new Date(+parts[0], +parts[1] - 1, +parts[2]);
    if (isNaN(submit.getTime())) return;
    var deadline = workingDay(submit, 7);
    var escalate = workingDay(submit, 8);
    /* полоса: с понедельника недели подачи, 3 недели */
    var start = addDays(submit, -((submit.getDay() + 6) % 7));
    strip.innerHTML = '';
    strip.classList.add('w3');
    var counter = 0;
    for (var i = 0; i < 21; i++) {
      var d = addDays(start, i);
      var li = document.createElement('li');
      var cls = ['day'];
      var tag = '';
      var off = isOff(d);
      if (off) { cls.push('off'); if (d.getDay() !== 0 && d.getDay() !== 6) tag = 'празд\u00ADник'; }
      if (sameDay(d, submit)) { cls.push('submit'); tag = 'подача'; }
      if (d > submit && !off && d <= escalate) { counter++; cls.push('count'); }
      if (sameDay(d, deadline)) { cls.push('deadline'); tag = '7-й день'; }
      if (sameDay(d, escalate)) { cls.push('escalate'); tag = '8-й день'; }
      li.className = cls.join(' ');
      li.setAttribute('aria-label', fmt(d) + (tag ? ', ' + tag : '') + (off ? ', нерабочий день' : ''));
      li.innerHTML = '<span class="wd">' + WD[d.getDay()] + '</span><span class="dn"' + (cls.indexOf('count') !== -1 ? ' data-n="' + counter + '"' : '') + '>' + d.getDate() + '</span>' + (tag ? '<span class="tag">' + tag + '</span>' : '');
      strip.appendChild(li);
    }
    summary.textContent = 'Подача ' + fmt(submit) + '. Срок ответа банка: ' + fmt(deadline) + ' (7 рабочих дней, п. 13.4 ст. 7 115-ФЗ). С ' + fmt(escalate) + ' срок истёк: напоминание банку и жалоба в Банк России.';
    strip.dataset.deadline = fmt(deadline);
    strip.dataset.escalate = fmt(escalate);
    strip.dataset.submit = fmt(submit);
  }
  dateInput.addEventListener('change', renderStrip);
  dateInput.addEventListener('input', renderStrip);
  renderStrip();

  /* Состояния */
  var states = document.querySelectorAll('.state');
  var radios = document.querySelectorAll('input[name="state"]');
  var form = document.getElementById('paste-form');
  var input = document.getElementById('letter-input');
  var errorText = document.getElementById('letter-error');
  var bar = document.querySelector('.progress-bar');
  var timer = null;

  function show(name) {
    states.forEach(function (el) { el.hidden = el.getAttribute('data-state') !== name; });
    radios.forEach(function (r) { r.checked = r.value === name; });
    if (name === 'loading') { bar.classList.remove('run'); void bar.offsetWidth; bar.classList.add('run'); }
    if (name !== 'result') clearActive();
  }
  function startParsing() {
    show('loading');
    clearTimeout(timer);
    timer = setTimeout(function () {
      show('result');
      document.querySelector('.date-row').scrollIntoView({ block: 'start' });
    }, 1200);
  }
  radios.forEach(function (r) { r.addEventListener('change', function () { clearTimeout(timer); show(r.value); }); });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!input.value.trim()) { errorText.hidden = false; input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
    errorText.hidden = true; input.removeAttribute('aria-invalid'); startParsing();
  });
  input.addEventListener('input', function () { if (input.value.trim()) { errorText.hidden = true; input.removeAttribute('aria-invalid'); } });
  document.getElementById('fill-example').addEventListener('click', function () { input.value = EXAMPLE_TEXT; errorText.hidden = true; input.removeAttribute('aria-invalid'); input.focus(); });
  document.getElementById('hero-example').addEventListener('click', function () { input.value = EXAMPLE_TEXT; document.getElementById('razbor').scrollIntoView({ block: 'start' }); startParsing(); });
  document.getElementById('retry').addEventListener('click', startParsing);
  document.getElementById('back-to-text').addEventListener('click', function () { show('empty'); input.focus(); });
  document.getElementById('another').addEventListener('click', function () { show('empty'); input.value = ''; input.focus(); });

  /* Связь строка ↔ цитата */
  var marks = document.querySelectorAll('mark[role="button"]');
  var rows = document.querySelectorAll('.fields tr[data-f]');
  function clearActive() {
    marks.forEach(function (m) { m.classList.remove('is-active'); m.setAttribute('aria-pressed', 'false'); });
    rows.forEach(function (r) { r.classList.remove('is-active'); });
  }
  function activate(field, from) {
    clearActive();
    var ms = document.querySelectorAll('mark[data-f="' + field + '"]');
    var row = document.querySelector('.fields tr[data-f="' + field + '"]');
    ms.forEach(function (m) { m.classList.add('is-active'); m.setAttribute('aria-pressed', 'true'); });
    if (row) row.classList.add('is-active');
    if (from === 'row' && ms.length) ms[0].scrollIntoView({ block: 'center' });
    if (from === 'mark' && row) row.scrollIntoView({ block: 'nearest' });
  }
  marks.forEach(function (m) {
    m.addEventListener('click', function () { activate(m.getAttribute('data-f'), 'mark'); });
    m.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(m.getAttribute('data-f'), 'mark'); } });
  });
  rows.forEach(function (r) {
    if (!r.hasAttribute('tabindex')) return;
    r.addEventListener('click', function () { activate(r.getAttribute('data-f'), 'row'); });
    r.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(r.getAttribute('data-f'), 'row'); } });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') clearActive(); });

  /* Прямая ссылка на состояние: ?state=result */
  var wanted = new URLSearchParams(location.search).get('state');
  if (wanted && ['empty', 'loading', 'error', 'result'].indexOf(wanted) !== -1) {
    show(wanted); /* прокрутку к разделу даёт якорь #razbor в ссылке */
  }

  /* Копирование */
  var feedback = document.querySelector('.copy-feedback');
  document.getElementById('copy-result').addEventListener('click', function () {
    var lines = [];
    rows.forEach(function (r) {
      lines.push(r.querySelector('th').textContent.trim() + ': ' + r.querySelector('td').textContent.trim());
    });
    lines.push('Подача документов: ' + strip.dataset.submit + '; срок ответа банка: ' + strip.dataset.deadline + ' (7 раб. дней, п. 13.4); напоминание и жалоба в ЦБ: ' + strip.dataset.escalate + '.');
    var text = 'Разбор запроса (Навигатор-115, пример 1 корпуса Pulsar)\n' + lines.join('\n');
    var okText = 'Скопировано: ' + rows.length + ' полей и сроки.';
    var failText = 'Скопировать не удалось: браузер не дал доступ к буферу обмена. Выделите таблицу и скопируйте вручную.';
    function legacyCopy() {
      /* запасной путь, если асинхронный буфер недоступен (встроенные панели, старые браузеры) */
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.left = '-9999px';
      document.body.appendChild(ta); ta.select();
      var done = false;
      try { done = document.execCommand('copy'); } catch (e) { done = false; }
      document.body.removeChild(ta);
      feedback.textContent = done ? okText : failText;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { feedback.textContent = okText; }, legacyCopy);
    } else { legacyCopy(); }
  });
})();
