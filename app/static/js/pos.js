(() => {
  const root = document.querySelector('[data-pos]');
  if (!root) return;
  const money = { format: (value) => `G. ${Math.round(value).toLocaleString('es-PY')}` };
  const lines = new Map();
  const container = root.querySelector('#cart-lines');
  const totalNode = root.querySelector('#cart-total');
  const countNodes = [root.querySelector('#cart-count'), root.querySelector('#checkout-count')];
  const chargeButton = root.querySelector('#charge-sale');
  const search = root.querySelector('#product-search');
  const category = root.querySelector('#category-filter');
  const barcode = root.querySelector('#pos-barcode');
  const pixPanel = root.querySelector('[data-pix-panel]');

  const render = () => {
    const count = [...lines.values()].reduce((sum, line) => sum + line.qty, 0);
    if (!lines.size) {
      container.innerHTML = '<div class="empty cart-empty"><b>Escaneá o elegí productos para comenzar</b><span>La cantidad se controla después de agregar.</span></div>';
    } else {
      container.innerHTML = [...lines.values()].map((line) => `<div class="cart-line" data-line="${line.id}"><span><b>${line.name}</b><small>${money.format(line.price)} por unidad</small></span><div class="quantity-control"><button type="button" data-minus="${line.id}" aria-label="Restar">−</button><b>${line.qty}</b><button type="button" data-plus="${line.id}" aria-label="Sumar">＋</button></div><strong>${money.format(line.price)}</strong><strong>${money.format(line.price * line.qty)}</strong><button class="remove" type="button" data-remove="${line.id}" aria-label="Eliminar">×</button></div>`).join('');
    }
    const total = [...lines.values()].reduce((sum, line) => sum + line.price * line.qty, 0);
    totalNode.textContent = money.format(total);
    countNodes.forEach((node) => { if (node) node.textContent = count; });
  };

  const addProduct = (button) => {
    const id = Number(button.dataset.productId);
    const current = lines.get(id) || { id, name: button.dataset.name, price: Number(button.dataset.price), stock: Number(button.dataset.stock), qty: 0 };
    if (current.qty >= current.stock) return window.Profut.notify('No hay más stock disponible para este producto.', 'warning', 'Stock insuficiente');
    current.qty += 1;
    lines.set(id, current);
    render();
  };
  root.querySelectorAll('.pos-product').forEach((button) => button.addEventListener('click', () => addProduct(button)));

  const addByBarcode = () => {
    const code = barcode?.value.trim() || search?.value.trim();
    if (!code) return;
    const product = [...root.querySelectorAll('.pos-product')].find((button) => button.dataset.barcode === code);
    if (!product) return window.Profut.notify(`No existe un producto activo con el código ${code}.`, 'danger', 'Código no encontrado');
    if (product.disabled) return window.Profut.notify(`${product.dataset.name} no tiene stock disponible.`, 'warning', 'Producto agotado');
    addProduct(product);
    barcode.value = '';
    search.value = '';
    barcode.focus();
  };
  barcode?.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); addByBarcode(); } });
  barcode?.addEventListener('barcode:scanned', addByBarcode);
  search?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && search.value.trim()) {
      const exact = [...root.querySelectorAll('.pos-product')].find((button) => button.dataset.barcode === search.value.trim());
      if (exact) { event.preventDefault(); addProduct(exact); search.value = ''; }
    }
  });

  container.addEventListener('click', (event) => {
    const id = Number(event.target.dataset.plus || event.target.dataset.minus || event.target.dataset.remove);
    if (!id) return;
    const line = lines.get(id);
    if (event.target.dataset.plus) {
      if (line.qty >= line.stock) return window.Profut.notify('Llegaste al stock disponible.', 'warning', line.name);
      line.qty += 1;
    }
    if (event.target.dataset.minus) line.qty -= 1;
    if (event.target.dataset.remove || line.qty <= 0) lines.delete(id);
    render();
  });
  root.querySelector('#clear-cart')?.addEventListener('click', () => { lines.clear(); render(); });

  const filterProducts = () => root.querySelectorAll('.pos-product').forEach((button) => {
    const needle = search.value.toLowerCase();
    const matchesText = `${button.dataset.name} ${button.dataset.barcode}`.toLowerCase().includes(needle);
    const matchesCategory = !category.value || button.dataset.category === category.value;
    button.hidden = !(matchesText && matchesCategory);
  });
  search?.addEventListener('input', filterProducts);
  category?.addEventListener('change', filterProducts);
  root.querySelectorAll('[name="sale-method"]').forEach((input) => input.addEventListener('change', () => {
    if (pixPanel) pixPanel.hidden = input.value !== 'PIX' || !input.checked;
  }));

  chargeButton?.addEventListener('click', async () => {
    if (!lines.size) return window.Profut.notify('Agregá al menos un producto antes de cobrar.', 'warning', 'Venta vacía');
    chargeButton.disabled = true;
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    const payload = {
      items: [...lines.values()].map((line) => ({ product_id: line.id, qty: line.qty })),
      method: root.querySelector('[name="sale-method"]:checked').value,
      reference: root.querySelector('#sale-reference').value,
      idempotency_key: root.dataset.idempotency,
    };
    try {
      const response = await fetch('/pos/venta', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'No se pudo confirmar la venta.');
      window.location.assign(result.ticket_url);
    } catch (error) {
      window.Profut.notify(error.message, 'danger', 'No se confirmó la venta');
      chargeButton.disabled = false;
    }
  });
  render();
})();

(() => {
  const workspace = document.querySelector('.account-workspace');
  if (!workspace) return;
  const barcode = workspace.querySelector('#account-barcode');
  const submitByBarcode = () => {
    const code = barcode.value.trim();
    if (!code) return;
    const form = [...workspace.querySelectorAll('[data-account-product]')].find((row) => row.dataset.barcode === code);
    if (!form) return window.Profut.notify(`No existe un producto activo con el código ${code}.`, 'danger', 'Código no encontrado');
    const button = form.querySelector('button');
    if (button?.disabled) return window.Profut.notify('El producto no tiene stock disponible.', 'warning', 'Producto agotado');
    form.requestSubmit(button);
  };
  barcode?.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); submitByBarcode(); } });
  barcode?.addEventListener('barcode:scanned', submitByBarcode);

  workspace.addEventListener('click', async (event) => {
    const quantityButton = event.target.closest('[data-item-quantity]');
    const removeButton = event.target.closest('[data-remove-item]');
    if (!quantityButton && !removeButton) return;
    if (removeButton) {
      const confirmed = await window.Profut.confirm('¿Querés quitar este consumo? El stock se repondrá automáticamente.', 'Quitar producto');
      if (!confirmed) return;
    }
    const url = quantityButton?.dataset.itemQuantity || removeButton.dataset.removeItem;
    const fields = quantityButton ? { delta: quantityButton.dataset.delta } : {};
    await window.Profut.postAndRefresh(url, fields, { preserveScroll: true });
  });

  const methods = workspace.querySelectorAll('[data-payment-method]');
  const pixPanel = workspace.querySelector('[data-pix-panel]');
  const updateMethod = () => {
    const selected = workspace.querySelector('[data-payment-method]:checked');
    if (pixPanel) pixPanel.hidden = selected?.value !== 'PIX';
  };
  methods.forEach((method) => method.addEventListener('change', updateMethod));
  updateMethod();
})();
