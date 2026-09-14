if (!window.profutShortcutsBound) {
  window.profutShortcutsBound = true;
  document.addEventListener('keydown', (event) => {
    if (!location.pathname.startsWith('/pos')) return;
    const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
    if (event.key === 'F3') { event.preventDefault(); document.querySelector('#product-search, [data-account-search]')?.focus(); }
    if (event.key === 'F4') { event.preventDefault(); window.Profut.navigate('/pos?mode=account'); }
    if (event.key === 'F2') { event.preventDefault(); window.Profut.navigate('/pos?mode=sale'); }
    if (event.key === 'F8' && !typing) { event.preventDefault(); document.querySelector('[name="scope"][value="selected"]')?.click(); }
    if (event.key === 'F9' && !typing) { event.preventDefault(); (document.querySelector('#charge-sale') || document.querySelector('[name="scope"][value="all"]'))?.click(); }
    if (event.key === 'Escape') document.querySelector('dialog[open]')?.close();
  });
}
