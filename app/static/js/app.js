(() => {
  const qs = (selector, parent = document) => parent.querySelector(selector);
  const qsa = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const csrf = () => qs('meta[name="csrf-token"]')?.content || '';
  let navigationController = null;

  const notify = (message, type = 'info', title = '') => {
    let stack = qs('.flash-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'flash-stack';
      stack.setAttribute('role', 'status');
      document.body.append(stack);
    }
    const labels = { success: 'Listo', danger: 'No se pudo completar', warning: 'Atención', info: 'Información' };
    const icons = { success: '✓', danger: '!', warning: '!', info: 'i' };
    const flash = document.createElement('div');
    flash.className = `flash ${type}`;
    flash.innerHTML = `<i>${icons[type] || 'i'}</i><span><b></b><small></small></span><button type="button" data-dismiss aria-label="Cerrar">×</button>`;
    flash.querySelector('b').textContent = title || labels[type] || 'PROFUT';
    flash.querySelector('small').textContent = message;
    stack.append(flash);
    window.setTimeout(() => flash.remove(), 6500);
    return flash;
  };

  const confirmAction = (message, title = 'Confirmar acción') => new Promise((resolve) => {
    const dialog = qs('#profut-confirm-dialog');
    if (!dialog) return resolve(false);
    qs('[data-confirm-title]', dialog).textContent = title;
    qs('[data-confirm-message]', dialog).textContent = message;
    dialog.returnValue = '';
    dialog.showModal();
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
  });

  const runPageScripts = async (parsed) => {
    qsa('script[data-page-script]').forEach((script) => script.remove());
    const scripts = qsa('script', parsed).filter((script) => !script.src.includes('/static/js/app.js'));
    for (const source of scripts) {
      const script = document.createElement('script');
      script.dataset.pageScript = 'true';
      if (source.src) {
        script.src = source.src;
        await new Promise((resolve) => {
          script.onload = resolve;
          script.onerror = resolve;
          document.body.append(script);
        });
      } else if (source.textContent.trim()) {
        script.textContent = source.textContent;
        document.body.append(script);
      }
    }
  };

  const applyDocument = async (html, finalUrl, options = {}) => {
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const nextContent = qs('main.content', parsed);
    if (!nextContent) {
      window.location.assign(finalUrl);
      return;
    }
    const scrollTop = window.scrollY;
    const swap = () => {
      qs('main.content').innerHTML = nextContent.innerHTML;
      const nextDesktopNav = qs('.main-nav', parsed);
      const nextMobileNav = qs('.mobile-nav', parsed);
      if (nextDesktopNav) qs('.main-nav').innerHTML = nextDesktopNav.innerHTML;
      if (nextMobileNav) qs('.mobile-nav').innerHTML = nextMobileNav.innerHTML;
      document.title = parsed.title;
      const nextCsrf = qs('meta[name="csrf-token"]', parsed)?.content;
      if (nextCsrf) qs('meta[name="csrf-token"]').content = nextCsrf;
      qs('#sidebar')?.classList.remove('open');
      document.body.classList.remove('sidebar-open', 'page-loading');
    };
    if (document.startViewTransition) await document.startViewTransition(swap).finished;
    else swap();
    if (options.history === 'push') history.pushState({}, '', finalUrl);
    if (options.history === 'replace') history.replaceState({}, '', finalUrl);
    await runPageScripts(parsed);
    window.scrollTo({ top: options.preserveScroll ? scrollTop : 0, behavior: 'instant' });
    window.setTimeout(() => qsa('.flash-stack .flash').forEach((flash) => flash.remove()), 6500);
  };

  const navigate = async (url, options = {}) => {
    navigationController?.abort();
    navigationController = new AbortController();
    document.body.classList.add('page-loading');
    try {
      const response = await fetch(url, { signal: navigationController.signal, headers: { 'X-Profut-Navigation': '1' } });
      if (!response.ok) throw new Error(`Respuesta ${response.status}`);
      await applyDocument(await response.text(), response.url, { history: options.history || 'push', preserveScroll: options.preserveScroll });
    } catch (error) {
      document.body.classList.remove('page-loading');
      if (error.name !== 'AbortError') window.location.assign(url);
    }
  };

  const submitAsync = async (form, submitter, options = {}) => {
    const data = new FormData(form);
    if (submitter?.name) data.set(submitter.name, submitter.value);
    const method = (submitter?.getAttribute('formmethod') || form.method || 'POST').toUpperCase();
    let action = submitter?.getAttribute('formaction') || form.action;
    if (method === 'GET') {
      const target = new URL(action, window.location.href);
      target.search = new URLSearchParams(data).toString();
      action = target.href;
    }
    form.classList.add('is-submitting');
    if (submitter) submitter.disabled = true;
    try {
      const response = await fetch(action, {
        method,
        body: method === 'GET' ? undefined : data,
        headers: { 'X-Profut-Navigation': '1' },
      });
      if (!response.ok) throw new Error(`Respuesta ${response.status}`);
      await applyDocument(await response.text(), response.url, { history: options.history || 'replace', preserveScroll: options.preserveScroll });
    } catch (_error) {
      form.classList.remove('is-submitting');
      if (submitter) submitter.disabled = false;
      notify('La conexión se interrumpió. No se confirmó ningún cambio; volvé a intentar.', 'danger', 'Problema de conexión');
    }
  };

  const postAndRefresh = async (url, fields = {}, options = {}) => {
    const data = new FormData();
    data.set('csrf_token', csrf());
    Object.entries(fields).forEach(([key, value]) => data.set(key, value));
    try {
      const response = await fetch(url, { method: 'POST', body: data, headers: { 'X-Profut-Navigation': '1' } });
      if (!response.ok) throw new Error(`Respuesta ${response.status}`);
      await applyDocument(await response.text(), response.url, { history: 'replace', preserveScroll: options.preserveScroll });
      return true;
    } catch (_error) {
      notify('No se pudo guardar el cambio. Revisá tu conexión e intentá nuevamente.', 'danger');
      return false;
    }
  };

  window.Profut = { notify, confirm: confirmAction, navigate, postAndRefresh };

  // Scripts attached by the initial server render are page scripts and must be replaced on navigation.
  qsa('body > script').forEach((script) => { if (!script.src.includes('/static/js/app.js')) script.dataset.pageScript = 'initial'; });

  document.addEventListener('click', async (event) => {
    const sidebarToggle = event.target.closest('[data-toggle-sidebar]');
    if (sidebarToggle) {
      qs('#sidebar')?.classList.toggle('open');
      document.body.classList.toggle('sidebar-open');
      return;
    }
    const dialogOpen = event.target.closest('[data-dialog-open]');
    if (dialogOpen) { qs(`#${dialogOpen.dataset.dialogOpen}`)?.showModal(); return; }
    const dialogClose = event.target.closest('[data-dialog-close]');
    if (dialogClose) { dialogClose.closest('dialog')?.close(); return; }
    const dismiss = event.target.closest('[data-dismiss]');
    if (dismiss) { dismiss.closest('.flash')?.remove(); return; }
    const password = event.target.closest('[data-password-toggle]');
    if (password) {
      const input = qs(`#${password.dataset.passwordToggle}`);
      if (input) input.type = input.type === 'password' ? 'text' : 'password';
      return;
    }
    const themeButton = event.target.closest('[data-theme-toggle]');
    if (themeButton) {
      const theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('profut-theme', theme);
      try {
        await fetch(themeButton.dataset.themeUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify({ theme }) });
      } catch (_error) { notify('El tema se guardará cuando vuelva la conexión.', 'warning'); }
      return;
    }
    const anchor = event.target.closest('a[href]');
    if (!anchor || anchor.dataset.noSpa !== undefined || anchor.target || anchor.hasAttribute('download') || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    const url = new URL(anchor.href, window.location.href);
    if (url.origin !== window.location.origin || url.hash || url.pathname.startsWith('/static/') || anchor.closest('.receipt-actions')) return;
    event.preventDefault();
    navigate(url.href);
  });

  document.addEventListener('click', (event) => {
    if (event.target.tagName === 'DIALOG') event.target.close();
  });

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    const submitter = event.submitter;
    if (form.dataset.confirm && !form.dataset.confirmed) {
      event.preventDefault();
      const confirmed = await confirmAction(form.dataset.confirm, form.dataset.confirmTitle || 'Confirmar acción');
      if (confirmed) {
        form.dataset.confirmed = 'true';
        form.requestSubmit(submitter || undefined);
        window.setTimeout(() => delete form.dataset.confirmed, 0);
      }
      return;
    }
    if (form.dataset.async !== undefined) {
      event.preventDefault();
      submitAsync(form, submitter, { preserveScroll: form.dataset.preserveScroll !== undefined });
    }
  });

  document.addEventListener('input', (event) => {
    const input = event.target.closest('[data-master-search], [data-account-search], [data-product-account-search]');
    if (!input) return;
    const map = input.matches('[data-master-search]') ? ['[data-master-row]', 'masterRow'] : input.matches('[data-account-search]') ? ['[data-account-row]', 'accountRow'] : ['[data-account-product]', 'accountProduct'];
    qsa(map[0]).forEach((row) => {
      const haystack = (row.dataset[map[1]] || row.textContent).toLowerCase();
      row.hidden = !haystack.includes(input.value.trim().toLowerCase());
    });
  });

  const updateClock = () => qsa('[data-live-clock]').forEach((node) => {
    node.dateTime = new Date().toISOString();
    node.textContent = new Intl.DateTimeFormat('es-PY', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
  });
  updateClock();
  window.setInterval(updateClock, 1000);
  window.addEventListener('popstate', () => navigate(window.location.href, { history: 'none' }));
  window.setTimeout(() => qsa('.flash-stack .flash').forEach((flash) => flash.remove()), 6500);
})();
