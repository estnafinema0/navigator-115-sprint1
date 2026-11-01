/* Направление C: состояния, связь «панель ↔ цитата», копирование маршрутного листа.
   Бэкенда нет: разбор примера подготовлен заранее по корпусу Pulsar (пример 4). */
(function () {
  'use strict';

  var EXAMPLE_TEXT =
    '«Мы ограничили доступ к деньгам из личного кабинета и заблокировали карты… У нас появились вопросы об источнике денег на вашем счете, налогах и переводах… Чтобы снять ограничения, проверим выписки с расчетного, валютного и карточных счетов… Если вдруг вопросы останутся, возможно, предложим закрыть счет».';

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
      document.querySelector('.sign-here').scrollIntoView({ block: 'start' });
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

  /* Связь панель ↔ цитата */
  var marks = document.querySelectorAll('mark[role="button"]');
  var panels = document.querySelectorAll('.panel');
  function clearActive() {
    marks.forEach(function (m) { m.classList.remove('is-active'); m.setAttribute('aria-pressed', 'false'); });
    panels.forEach(function (p) { p.classList.remove('is-active'); });
  }
  function activate(field, from) {
    clearActive();
    var mark = document.querySelector('mark[data-f="' + field + '"]');
    var panel = document.querySelector('.panel[data-f="' + field + '"]');
    if (mark) { mark.classList.add('is-active'); mark.setAttribute('aria-pressed', 'true'); }
    if (panel) panel.classList.add('is-active');
    if (from === 'panel' && mark) mark.scrollIntoView({ block: 'center' });
    if (from === 'mark' && panel) panel.scrollIntoView({ block: 'nearest' });
  }
  marks.forEach(function (m) {
    m.addEventListener('click', function () { activate(m.getAttribute('data-f'), 'mark'); });
    m.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(m.getAttribute('data-f'), 'mark'); } });
  });
  document.querySelectorAll('[data-show]').forEach(function (b) {
    b.addEventListener('click', function () { activate(b.getAttribute('data-show'), 'panel'); });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') clearActive(); });

  /* Прямая ссылка на состояние: ?state=result */
  var wanted = new URLSearchParams(location.search).get('state');
  if (wanted && ['empty', 'loading', 'error', 'result'].indexOf(wanted) !== -1) {
    show(wanted); /* прокрутку к разделу даёт якорь #razbor в ссылке */
  }

  /* Копирование маршрутного листа */
  var feedback = document.querySelector('.copy-feedback');
  document.getElementById('copy-result').addEventListener('click', function () {
    var lines = [];
    panels.forEach(function (p) {
      var ps = Array.prototype.map.call(p.querySelectorAll('p'), function (x) { return x.textContent.trim(); });
      lines.push(p.querySelector('h4').textContent.trim() + ': ' + ps.join(' '));
    });
    document.querySelectorAll('.route-list .sign').forEach(function (s) {
      lines.push((s.classList.contains('sign-no') ? 'Недопустимо: ' : 'Допустимо: ') + s.querySelector('.rt').textContent.trim() + '. ' + s.querySelectorAll('p')[1].textContent.trim());
    });
    var text = 'Маршрутный лист (Навигатор-115, пример 4 корпуса Pulsar)\n' + lines.join('\n');
    var okText = 'Скопировано: ' + panels.length + ' полей и 5 маршрутов.';
    var failText = 'Скопировать не удалось: браузер не дал доступ к буферу обмена. Выделите панели и скопируйте вручную.';
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
