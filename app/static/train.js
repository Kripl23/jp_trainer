/* Цикл тренировки: next -> answer -> reveal -> next. */
const $ = (id) => document.getElementById(id);

const answerInput = $("answer");
const form = $("answer-form");
const mark = $("mark");

let current = null;      // карточка с /session/next
let revealed = false;    // показан ли ответ (Enter = дальше)
let stats = { ok: 0, bad: 0 };

if (DIRECTION === "ru_jp" && window.wanakana) {
  wanakana.bind(answerInput, { IMEMode: true });
}

async function nextCard() {
  const params = new URLSearchParams({ source: SOURCE, level: LEVEL, direction: DIRECTION });
  const card = await (await fetch(`/api/session/next?${params}`)).json();

  mark.className = "mark";
  mark.textContent = "";
  $("reveal").hidden = true;
  revealed = false;

  if (card.done) {
    $("card-area").hidden = true;
    $("done-box").hidden = false;
    $("due-left").textContent = 0;
    $("new-left").textContent = 0;
    $("summary").innerHTML = stats.ok + stats.bad
      ? `верно <b class="ok">${stats.ok}</b> · неверно <b class="bad">${stats.bad}</b>`
      : "";
    return;
  }

  current = card;
  $("due-left").textContent = card.due_left;
  $("new-left").textContent = card.new_left;

  const prompt = $("prompt");
  prompt.textContent = card.prompt;
  prompt.className = "prompt" + (DIRECTION === "jp_ru" ? " jp" : "");
  $("prompt-sub").textContent = card.pos ? `(${card.pos})` : "";

  answerInput.value = "";
  answerInput.disabled = false;
  $("submit-btn").textContent = "Ответить";
  answerInput.focus();
}

async function submitAnswer() {
  const answer = answerInput.value.trim();
  if (!answer) return;

  const res = await fetch("/api/session/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word_id: current.word_id, direction: DIRECTION, answer }),
  });
  const result = await res.json();

  stats[result.correct ? "ok" : "bad"]++;
  $("session-count").textContent = stats.ok + stats.bad;

  mark.textContent = result.correct ? "○" : "✕"; // ◯ / ✕
  mark.className = "mark show " + (result.correct ? "maru" : "batsu");

  const jp = result.kanji
    ? `<span class="jp">${result.kanji}</span><span class="kana">${result.kana}</span>`
    : `<span class="jp">${result.kana}</span>`;
  const note = result.correct
    ? ""
    : `<div class="wrong-note">слово вернётся в этой сессии</div>`;
  $("reveal").innerHTML = `${jp} — <span class="ru">${result.ru}</span>${note}`;
  $("reveal").hidden = false;

  answerInput.disabled = true;
  $("submit-btn").textContent = "Дальше";
  revealed = true;
  $("submit-btn").focus();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  revealed ? nextCard() : submitAnswer();
});

nextCard();
