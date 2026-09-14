(() => {
  const dialog = document.querySelector('#barcode-scanner');
  const video = document.querySelector('#barcode-video');
  const message = document.querySelector('#scanner-message');
  if (!dialog || !video) return;
  let stream = null;
  let detector = null;
  let target = null;
  let active = false;

  const stop = () => {
    active = false;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    if (dialog.open) dialog.close();
  };
  const scan = async () => {
    if (!active || !detector) return;
    try {
      const codes = await detector.detect(video);
      if (codes.length) {
        target.value = codes[0].rawValue;
        target.dispatchEvent(new Event('input', { bubbles: true }));
        target.dispatchEvent(new CustomEvent('barcode:scanned', { bubbles: true, detail: codes[0].rawValue }));
        stop();
        return;
      }
    } catch (_error) {}
    window.requestAnimationFrame(scan);
  };

  document.querySelectorAll('[data-open-scanner]').forEach((button) => button.addEventListener('click', async () => {
    target = document.querySelector(`#${button.dataset.openScanner}`);
    if (!('BarcodeDetector' in window)) {
      window.Profut.notify('Este navegador no ofrece escaneo por cámara. Podés usar el lector físico o escribir el código.', 'warning', 'Cámara no disponible');
      target?.focus();
      return;
    }
    try {
      detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'qr_code'] });
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      video.srcObject = stream;
      await video.play();
      active = true;
      message.textContent = 'Apuntá la cámara al código de barras.';
      dialog.showModal();
      scan();
    } catch (_error) {
      stop();
      window.Profut.notify('No se pudo abrir la cámara. Revisá el permiso del navegador.', 'danger', 'Permiso de cámara');
    }
  }));
  document.querySelectorAll('[data-scanner-close]').forEach((button) => button.addEventListener('click', stop));
  dialog.addEventListener('cancel', stop);
})();
