(() => {
  const root = document.querySelector('[data-cash-count]');
  if (!root) return;
  const format = (value) => `G. ${Math.round(value).toLocaleString('es-PY')}`;
  const sync = () => {
    const total = [...root.querySelectorAll('[data-denomination]')].reduce(
      (sum, input) => sum + Number(input.value || 0) * Number(input.dataset.denomination), 0,
    );
    root.querySelector('[data-counted-total]').value = total;
    root.querySelectorAll('[data-count-preview]').forEach((node) => { node.textContent = format(total); });
    const difference = root.querySelector('[data-count-difference]');
    const delta = total - Number(difference.dataset.expected || 0);
    difference.textContent = format(delta);
    difference.classList.toggle('positive', delta >= 0);
    difference.classList.toggle('warning-text', delta < 0);
  };
  root.addEventListener('input', (event) => { if (event.target.matches('[data-denomination]')) sync(); });
  sync();
})();
