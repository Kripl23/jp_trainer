// Тест по темам FE: вопросы с выбором ответа и тренировка терминов.
(function () {
  const $ = (id) => document.getElementById(id);
  const state = {questions: [], index: 0, correct: 0, mistakes: [], answered: false};
  const STATUS_LABELS = {known: 'знаю', learning: 'учу', hard: 'трудное'};

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  async function start() {
    const params = new URLSearchParams({
      topic: window.FE.topicId || '',
      mode: $('mode').value,
      count: $('count').value,
      direction: $('direction').value,
    });
    if ($('statuses').value) params.set('statuses', $('statuses').value);

    const data = await (await fetch('/api/fe/quiz?' + params)).json();
    if (!data.questions.length) {
      alert('Для выбранных настроек не нашлось вопросов.');
      return;
    }
    Object.assign(state, {questions: data.questions, index: 0, correct: 0, mistakes: []});
    $('setup').hidden = true;
    $('done').hidden = true;
    $('session').hidden = false;
    $('total').textContent = state.questions.length;
    render();
  }

  function render() {
    state.answered = false;
    const q = state.questions[state.index];
    $('n').textContent = state.index + 1;
    $('score').textContent = state.correct;
    $('kind-title').textContent = q.kind === 'term' ? 'термин' : 'вопрос';
    $('reveal').hidden = true;
    $('reveal').innerHTML = '';
    $('verdict').className = 'mark-big';
    $('verdict').textContent = '';

    const isJapanese = q.kind === 'term' && q.direction === 'ja_ru';
    $('prompt').innerHTML = isJapanese
      ? `<div class="jp-mid">${escapeHtml(q.question)}</div>`
      : `<div class="meaning">${escapeHtml(q.question)}</div>`;
    $('hint').textContent = q.sub || '';

    const options = $('options');
    options.innerHTML = '';
    q.options.forEach((option) => {
      const button = document.createElement('button');
      button.textContent = option;
      button.dataset.value = option;
      if (/[぀-ヿ一-鿿]/.test(option)) button.classList.add('jp');
      button.addEventListener('click', () => submit(option, button));
      options.appendChild(button);
    });
  }

  async function submit(value, button) {
    if (state.answered) return;
    state.answered = true;
    const q = state.questions[state.index];

    const data = await (await fetch('/api/fe/answer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind: q.kind, item_id: q.item_id, answer: value,
                            direction: q.direction || 'ja_ru'}),
    })).json();

    if (data.correct) state.correct += 1;
    else state.mistakes.push({q, expected: data.expected, given: value,
                              explanation: data.explanation});
    $('score').textContent = state.correct;
    $('verdict').textContent = data.correct ? '◯' : '✕';
    $('verdict').className = 'mark-big show ' + (data.correct ? 'maru' : 'batsu');

    $('options').querySelectorAll('button').forEach((b) => {
      b.disabled = true;
      if (b.dataset.value === data.expected) b.classList.add('ok');
      if (b === button && !data.correct) b.classList.add('bad');
    });

    const parts = [];
    if (data.explanation) parts.push(`<div class="why">${escapeHtml(data.explanation)}</div>`);
    if (q.kind === 'term') {
      const status = (data.mark && data.mark.status) || 'new';
      const buttons = Object.entries(STATUS_LABELS).map(([key, label]) =>
        `<button type="button" data-status="${key}" class="${status === key ? 'on' : ''}">${label}</button>`
      ).join('');
      parts.push(`<div class="mark-row"><span class="muted small">Отметить:</span>
        <span class="marks" data-item-type="fe_term" data-item-id="${escapeHtml(q.item_id)}">
          ${buttons}<button type="button" data-status="new" class="${status === 'new' ? 'on' : ''}">—</button>
        </span><button class="btn small" id="next-btn">Дальше</button></div>`);
    } else {
      parts.push('<div class="mark-row"><button class="btn small" id="next-btn">Дальше</button></div>');
    }
    $('reveal').innerHTML = parts.join('');
    $('reveal').hidden = false;
    const nextButton = $('next-btn');
    nextButton.addEventListener('click', next);
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
    $('session').hidden = true;
    $('done').hidden = false;
    const total = state.questions.length;
    const percent = Math.round((state.correct / total) * 100);
    $('final-score').textContent = percent + '%';
    $('final-detail').textContent = `${state.correct} из ${total} верно`;

    let passPercent = 80;
    if (window.FE.topicId && $('mode').value !== 'terms') {
      const res = await fetch(`/api/fe/topic/${window.FE.topicId}/complete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({correct: state.correct, total: total}),
      });
      if (res.ok) {
        const data = await res.json();
        passPercent = data.pass_percent;
        $('final-detail').textContent += data.completed
          ? ' · тема засчитана'
          : ` · для зачёта нужно ${passPercent}%`;
      }
    }
    $('final-score').className = 'score' + (percent >= passPercent ? ' pass' : '');

    $('mistakes').innerHTML = state.mistakes.length
      ? `<h2>Ошибки (${state.mistakes.length})</h2>` + state.mistakes.map((mistake) =>
          `<div class="card"><b>${escapeHtml(mistake.q.question)}</b>
           <div class="small">верно: ${escapeHtml(mistake.expected)} · ваш ответ: ${escapeHtml(mistake.given)}</div>
           ${mistake.explanation ? `<div class="muted small">${escapeHtml(mistake.explanation)}</div>` : ''}
           </div>`).join('')
      : '';
  }

  $('start').addEventListener('click', start);
  $('again').addEventListener('click', () => {
    $('done').hidden = true;
    $('setup').hidden = false;
  });
  document.addEventListener('keydown', (event) => {
    if ($('session').hidden) return;
    if (event.key === 'Enter' && state.answered) {
      event.preventDefault();
      next();
    } else if (!state.answered && /^[1-9]$/.test(event.key)) {
      const button = $('options').querySelectorAll('button')[Number(event.key) - 1];
      if (button) button.click();
    }
  });

  if (window.FE.mode === 'terms') $('mode').value = 'terms';
})();
