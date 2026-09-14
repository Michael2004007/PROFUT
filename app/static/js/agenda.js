(() => {
  const dialog = document.querySelector('#reservation-dialog');
  const input = document.querySelector('#reservation-start');
  const label = document.querySelector('#reservation-time');
  document.querySelectorAll('[data-book-slot]').forEach((button) => button.addEventListener('click', () => {
    input.value = button.dataset.bookSlot;
    label.textContent = button.dataset.bookSlot;
    dialog.showModal();
  }));
})();

