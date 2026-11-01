/* Направление A: переключение состояний, связь «пометка на полях ↔ цитата в письме», копирование разбора.
   Бэкенда нет: разбор примера подготовлен заранее по корпусу Pulsar (пример 2). */
(function () {
  'use strict';

  var EXAMPLE_TEXT =
    '«Пожалуйста, ответьте до 25.02.2026. Вы внесли на свой счет 5 000 000,00 ₽ … Предоставьте информацию об источнике происхождения денежных средств, которые вы внесли на счет … пришлите подтверждающие документы (2-НДФЛ, 3-НДФЛ, справку о доходах, подтверждение продажи движимого или недвижимого имущества и другие)».\n«Если вы не предоставите необходимую информацию, мы ограничим отдельные виды операций по вашему счету.»';

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
    if (name === 'loading') {
      bar.classList.remove('run');
      void bar.offsetWidth; /* перезапуск одноразовой анимации полосы */
      bar.classList.add('run');
    }
    if (name !== 'result') clearActive();
  }

  function startParsing(target) {
    show('loading');
    clearTimeout(timer);
    timer = setTimeout(function () {
      show(target || 'result');
      if (target === 'result' || !target) {
        var first = document.querySelector('.margin .note');
        if (first) first.scrollIntoView({ block: 'start' });
      }
    }, 1200);
  }

  radios.forEach(function (r) {
    r.addEventListener('change', function () {
      clearTimeout(timer);
      if (r.value === 'loading') { show('loading'); return; }
      show(r.value);
    });
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!input.value.trim()) {
      errorText.hidden = false;
      input.setAttribute('aria-invalid', 'true');
      input.focus();
      return;
    }
    errorText.hidden = true;
    input.removeAttribute('aria-invalid');
    startParsing('result');
  });

  input.addEventListener('input', function () {
    if (input.value.trim()) { errorText.hidden = true; input.removeAttribute('aria-invalid'); }
  });

  document.getElementById('fill-example').addEventListener('click', function () {
    input.value = EXAMPLE_TEXT;
    errorText.hidden = true;
    input.removeAttribute('aria-invalid');
    input.focus();
  });

  document.getElementById('hero-example').addEventListener('click', function () {
    input.value = EXAMPLE_TEXT;
    document.getElementById('razbor').scrollIntoView({ block: 'start' });
    startParsing('result');
  });

  document.getElementById('retry').addEventListener('click', function () { startParsing('result'); });
  document.getElementById('back-to-text').addEventListener('click', function () { show('empty'); input.focus(); });
  document.getElementById('another').addEventListener('click', function () {
    show('empty'); input.value = ''; input.focus();
  });

  /* Связь пометка ↔ цитата */
  var marks = document.querySelectorAll('mark[role="button"]');
  var notes = document.querySelectorAll('.note');

  function clearActive() {
    marks.forEach(function (m) { m.classList.remove('is-active'); m.setAttribute('aria-pressed', 'false'); });
    notes.forEach(function (n) { n.classList.remove('is-active'); });
  }

  function activate(field, from) {
    clearActive();
    var mark = document.querySelector('mark[data-f="' + field + '"]');
    var note = document.querySelector('.note[data-f="' + field + '"]');
    if (mark) { mark.classList.add('is-active'); mark.setAttribute('aria-pressed', 'true'); }
    if (note) note.classList.add('is-active');
    if (from === 'note' && mark) mark.scrollIntoView({ block: 'center' });
    if (from === 'mark' && note) note.scrollIntoView({ block: 'nearest' });
  }

  marks.forEach(function (m) {
    m.addEventListener('click', function () { activate(m.getAttribute('data-f'), 'mark'); });
    m.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(m.getAttribute('data-f'), 'mark'); }
    });
  });

  document.querySelectorAll('[data-show]').forEach(function (b) {
    b.addEventListener('click', function () { activate(b.getAttribute('data-show'), 'note'); });
  });

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') clearActive(); });

  /* Прямая ссылка на состояние: ?state=result (для ревью и скриншотов) */
  var wanted = new URLSearchParams(location.search).get('state');
  if (wanted && ['empty', 'loading', 'error', 'result'].indexOf(wanted) !== -1) {
    show(wanted); /* прокрутку к разделу даёт якорь #razbor в ссылке */
  }

  /* Копирование разбора как текста */
  var copyBtn = document.getElementById('copy-result');
  var feedback = document.querySelector('.copy-feedback');
  copyBtn.addEventListener('click', function () {
    var lines = [];
    notes.forEach(function (n) {
      var h = n.querySelector('h4').textContent.replace(/^\S+\s*/, '').trim();
      var ps = Array.prototype.map.call(n.querySelectorAll('p'), function (p) { return p.textContent.trim(); });
      lines.push(h + ': ' + ps.join(' '));
    });
    var text = 'Разбор запроса (Навигатор-115, пример 2 корпуса Pulsar)\n' + lines.join('\n');
    var okText = 'Разбор скопирован: ' + lines.length + ' полей.';
    var failText = 'Скопировать не удалось: браузер не дал доступ к буферу обмена. Выделите пометки и скопируйте вручную.';
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
