// Сессия теста: задания приходят с сервера пачкой, ответы проверяются по одному.
(function () {
  const $ = (id) => document.getElementById(id);
  const state = {questions: [], index: 0, correct: 0, mistakes: [], answered: false, picked: []};

  const el = {
    setup: $('setup'), session: $('session'), done: $('done'),
    n: $('n'), total: $('total'), score: $('score'), kindTitle: $('kind-title'),
    prompt: $('prompt'), hint: $('hint'), ask: $('ask'),
    options: $('options'), blockArea: $('block-area'),
    answerBlocks: $('answer-blocks'), bankBlocks: $('bank-blocks'),
    inputArea: $('input-area'), answer: $('answer'), check: $('check'),
    reveal: $('reveal'), verdict: $('verdict'),
  };

  const STATUS_LABELS = {known: 'знаю', learning: 'учу', hard: 'трудное'};

  function selectedKinds() {
    return [...document.querySelectorAll('input[name=kind]:checked')].map((i) => i.value);
  }

  async function start() {
    const params = new URLSearchParams({
      lesson_id: window.QUIZ.lessonId || '',
      mode: window.QUIZ.mode || 'lesson',
      kinds: selectedKinds().join(','),
      count: $('count').value,
    });
    const statuses = $('statuses');
    if (statuses && statuses.value) params.set('statuses', statuses.value);

    const res = await fetch('/api/jp/quiz?' + params);
    const data = await res.json();
    if (!data.questions.length) {
      alert('Для выбранных настроек не нашлось заданий — снимите ограничения или выберите другой урок.');
      return;
    }
    state.questions = data.questions;
    state.index = 0;
    state.correct = 0;
    state.mistakes = [];
    el.setup.hidden = true;
    el.done.hidden = true;
    el.session.hidden = false;
    el.total.textContent = state.questions.length;
    render();
  }

  function reset() {
    state.answered = false;
    state.picked = [];
    el.reveal.hidden = true;
    el.reveal.innerHTML = '';
    el.verdict.className = 'mark-big';
    el.verdict.textContent = '';
    el.options.hidden = true;
    el.options.innerHTML = '';
    el.blockArea.hidden = true;
    el.answerBlocks.innerHTML = '';
    el.bankBlocks.innerHTML = '';
    el.inputArea.hidden = true;
    el.answer.value = '';
    el.ask.textContent = '';
    el.hint.textContent = '';
  }

  function render() {
    reset();
    const q = state.questions[state.index];
    el.n.textContent = state.index + 1;
    el.score.textContent = state.correct;
    el.kindTitle.textContent = q.title;
    el.prompt.innerHTML = q.prompt_html || '';
    if (q.hint) el.hint.textContent = q.hint;
    if (q.ask) el.ask.textContent = 'Форма: ' + q.ask;

    if (q.options) {
      el.options.hidden = false;
      q.options.forEach((option, i) => {
        const button = document.createElement('button');
        button.textContent = option;
        button.dataset.value = option;
        if (isJapanese(option)) button.classList.add('jp');
        button.addEventListener('click', () => submit(option, button));
        el.options.appendChild(button);
      });
    } else if (q.blocks) {
      el.blockArea.hidden = false;
      q.blocks.forEach((text) => addBlock(text));
      el.inputArea.hidden = false;
      el.answer.hidden = true;
      el.check.textContent = 'Проверить';
    } else {
      el.inputArea.hidden = false;
      el.answer.hidden = false;
      el.answer.className = q.input === 'kana' ? '' : 'lat';
      if (q.input === 'kana' && window.wanakana) {
        window.wanakana.bind(el.answer, {IMEMode: true});
      }
      el.answer.focus();
    }
  }

  function isJapanese(text) {
    return /[぀-ヿ一-鿿]/.test(text);
  }

  function addBlock(text) {
    const button = document.createElement('button');
    button.textContent = text;
    button.addEventListener('click', () => {
      if (state.answered) return;
      if (button.parentElement === el.bankBlocks) {
        el.answerBlocks.appendChild(button);
      } else {
        el.bankBlocks.appendChild(button);
      }
    });
    el.bankBlocks.appendChild(button);
  }

  function currentAnswer() {
    const q = state.questions[state.index];
    if (q.blocks) {
      return [...el.answerBlocks.querySelectorAll('button')]
        .map((b) => b.textContent).join('');
    }
    return el.answer.value.trim();
  }

  async function submit(value, button) {
    if (state.answered) {
      next();
      return;
    }
    const q = state.questions[state.index];
    const answer = value !== undefined ? value : currentAnswer();
    if (!answer) return;
    state.answered = true;

    const res = await fetch('/api/jp/answer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        kind: q.kind, item_type: q.item_type, item_id: q.item_id,
        answer: answer, slot: q.slot ?? null, form: q.form || '',
      }),
    });
    const data = await res.json();

    if (data.correct) state.correct += 1;
    else state.mistakes.push({q, expected: data.expected, given: answer});
    el.score.textContent = state.correct;

    el.verdict.textContent = data.correct ? '◯' : '✕';
    el.verdict.className = 'mark-big show ' + (data.correct ? 'maru' : 'batsu');

    if (q.options) {
      el.options.querySelectorAll('button').forEach((b) => {
        b.disabled = true;
        const isRight = b.dataset.value === data.expected;
        if (isRight) b.classList.add('ok');
        if (b === button && !data.correct) b.classList.add('bad');
      });
    }
    showReveal(q, data, answer);
  }

  function showReveal(q, data, answer) {
    const parts = [];
    if (!data.correct) {
      parts.push(`<div class="expected">${escapeHtml(data.expected)}</div>`);
      parts.push(`<div class="why">ваш ответ: ${escapeHtml(answer) || '—'}</div>`);
    }
    if (data.explanation) parts.push(`<div class="why">${escapeHtml(data.explanation)}</div>`);
    if (data.note) parts.push(`<div class="note">${data.note}</div>`);

    const status = (data.mark && data.mark.status) || 'new';
    const buttons = Object.entries(STATUS_LABELS).map(([key, label]) =>
      `<button type="button" data-status="${key}" class="${status === key ? 'on' : ''}">${label}</button>`
    ).join('');
    parts.push(
      `<div class="mark-row"><span class="muted small">Отметить:</span>
        <span class="marks" data-item-type="${q.item_type}" data-item-id="${q.item_id}">
          ${buttons}<button type="button" data-status="new" class="${status === 'new' ? 'on' : ''}">—</button>
        </span>
        <button class="btn small" id="next-btn">Дальше</button></div>`);

    el.reveal.innerHTML = parts.join('');
    el.reveal.hidden = false;
    const nextButton = $('next-btn');
    if (nextButton) nextButton.addEventListener('click', next);
    nextButton.focus();
  }

  function next() {
    if (state.index + 1 >= state.questions.length) {
      finish();
      return;
    }
    state.index += 1;
    render();
  }

  async function finish() {
    el.session.hidden = true;
    el.done.hidden = false;
    const total = state.questions.length;
    const percent = Math.round((state.correct / total) * 100);
    $('final-score').textContent = percent + '%';
    $('final-detail').textContent = `${state.correct} из ${total} верно`;

    let passPercent = 80;
    if (window.QUIZ.lessonId) {
      const res = await fetch(`/api/jp/lesson/${window.QUIZ.lessonId}/complete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({correct: state.correct, total: total}),
      });
      if (res.ok) {
        const data = await res.json();
        passPercent = data.pass_percent;
        if (data.completed) {
          $('final-detail').textContent += ' · урок засчитан';
        } else {
          $('final-detail').textContent += ` · для зачёта нужно ${passPercent}%`;
        }
      }
    }
    $('final-score').className = 'score' + (percent >= passPercent ? ' pass' : '');

    if (state.mistakes.length) {
      const rows = state.mistakes.map((mistake) =>
        `<div class="card"><div class="ex-jp">${escapeHtml(mistake.expected)}</div>
         <div class="ex-ru">${escapeHtml(mistake.q.title)} · ваш ответ: ${escapeHtml(mistake.given) || '—'}</div>
         </div>`).join('');
      $('mistakes').innerHTML = `<h2>Ошибки (${state.mistakes.length})</h2>${rows}`;
    } else {
      $('mistakes').innerHTML = '';
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  $('start').addEventListener('click', start);
  $('again').addEventListener('click', () => {
    el.done.hidden = true;
    el.setup.hidden = false;
  });
  el.check.addEventListener('click', () => submit());

  document.addEventListener('keydown', (event) => {
    if (el.session.hidden) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      state.answered ? next() : submit();
    } else if (!state.answered && /^[1-9]$/.test(event.key)) {
      const buttons = el.options.querySelectorAll('button');
      const button = buttons[Number(event.key) - 1];
      if (button) button.click();
    }
  });

  // автостарт, если урок открыт сразу с параметрами
  if (new URLSearchParams(location.search).get('auto') === '1') start();
})();
