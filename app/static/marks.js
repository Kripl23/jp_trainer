// Ручные отметки «знаю / учу / трудное». Работает на любой странице:
// достаточно разметки <span class="marks" data-item-type data-item-id><button data-status>.
(function () {
  async function save(itemType, itemId, status) {
    const res = await fetch('/api/marks', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({item_type: itemType, item_id: itemId, status: status}),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('.marks button');
    if (!button) return;
    const group = button.closest('.marks');
    const {itemType, itemId} = group.dataset;
    const status = button.dataset.status;
    const previous = group.querySelector('button.on');
    group.querySelectorAll('button').forEach((b) => b.classList.remove('on'));
    button.classList.add('on');
    try {
      await save(itemType, itemId, status);
      group.dispatchEvent(new CustomEvent('mark:changed', {
        bubbles: true, detail: {itemType, itemId, status},
      }));
    } catch (err) {
      group.querySelectorAll('button').forEach((b) => b.classList.remove('on'));
      if (previous) previous.classList.add('on');
      console.error('не удалось сохранить отметку', err);
    }
  });

  window.saveMark = save;
})();
