(() => {
  const syncFormat = () => {
    const selected = document.querySelector('[name="format"]:checked, select[name="format"]');
    const groupOptions = document.querySelector('[data-group-options]');
    if (groupOptions) groupOptions.hidden = selected?.value !== 'GROUPS_KNOCKOUT';
  };
  document.querySelectorAll('[data-tournament-format]').forEach((input) => input.addEventListener('change', syncFormat));
  syncFormat();

  const syncMode = () => {
    const isNew = document.querySelector('[name="team_mode"]:checked')?.value === 'new';
    const existing = document.querySelector('[data-existing-team]');
    const fresh = document.querySelector('[data-new-team]');
    if (existing) existing.hidden = isNew;
    if (fresh) fresh.hidden = !isNew;
  };
  document.querySelectorAll('[name="team_mode"]').forEach((input) => input.addEventListener('change', syncMode));
  syncMode();

  const collect = document.querySelector('[data-collect-payment]');
  const payment = document.querySelector('[data-enrollment-payment]');
  const syncPayment = () => { if (payment) payment.hidden = !collect?.checked; };
  collect?.addEventListener('change', syncPayment);
  syncPayment();

  const scheduleDate = document.querySelector('[data-schedule-date]');
  scheduleDate?.addEventListener('change', () => {
    if (!scheduleDate.value) return;
    const url = `${window.location.pathname}?date=${encodeURIComponent(scheduleDate.value)}`;
    window.Profut?.navigate(url);
  });
})();
