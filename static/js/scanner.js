document.addEventListener('DOMContentLoaded', () => {
  const scanInput = document.getElementById('scanCode');
  const findButton = document.getElementById('findProductBtn');
  const openButton = document.getElementById('openScannerBtn');
  const message = document.getElementById('lookupMessage');
  const select = document.getElementById('productSelect');
  const reader = document.getElementById('reader');
  const stockBox = document.getElementById('stockAvailability');
  let scanner = null;

  const setMessage = (text, kind = '') => {
    message.textContent = text;
    message.className = `lookup-message ${kind}`;
  };

  async function findProduct(code) {
    const value = (code || '').trim();
    if (!value) {
      setMessage('Enter or scan a SKU/barcode first.', 'error-text');
      return;
    }
    setMessage('Looking up product…');
    try {
      const response = await fetch(`/api/product-lookup?code=${encodeURIComponent(value)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Product lookup failed.');
      select.value = String(data.id);
      if (typeof onProductChange === 'function') onProductChange();
      setMessage(`Found: ${data.name} (${data.sku}). Product selected.`, 'success-text');
      updateAvailability(data);
    } catch (error) {
      setMessage(error.message, 'error-text');
    }
  }

  function updateAvailability(productData = null) {
    if (!select.value) {
      stockBox.innerHTML = '<span class="availability-dot"></span><span>Select a product and warehouse to view available stock.</span>';
      return;
    }
    const selectedOption = select.options[select.selectedIndex];
    const sku = selectedOption?.dataset.sku;
    if (!sku) return;
    fetch(`/api/product-lookup?code=${encodeURIComponent(sku)}`)
      .then(response => response.json())
      .then(data => {
        const warehouseSelect = document.getElementById('warehouseSelect');
        const sourceSelect = document.getElementById('fromWarehouse');
        const activeWarehouseId = warehouseSelect?.value || sourceSelect?.value;
        if (!activeWarehouseId) {
          stockBox.innerHTML = `<span class="availability-dot"></span><span>${data.name}: choose a warehouse to view available stock.</span>`;
          return;
        }
        const level = data.stocks.find(item => String(item.warehouse_id) === String(activeWarehouseId));
        const quantity = level ? level.quantity : 0;
        stockBox.innerHTML = `<span class="availability-dot ${quantity > 0 ? 'dot-green' : 'dot-amber'}"></span><span><strong>${data.name}</strong> · ${level ? level.warehouse_name : 'Selected warehouse'} has <b>${quantity}</b> unit(s) available.</span>`;
      })
      .catch(() => {
        stockBox.innerHTML = '<span>Could not read current stock information.</span>';
      });
  }

  if (findButton) findButton.addEventListener('click', () => findProduct(scanInput.value));
  if (scanInput) scanInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      findProduct(scanInput.value);
    }
  });
  if (select) select.addEventListener('change', () => updateAvailability());
  ['warehouseSelect', 'fromWarehouse'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.addEventListener('change', () => updateAvailability());
  });

  if (openButton) {
    openButton.addEventListener('click', async () => {
      if (reader.hidden) {
        reader.hidden = false;
        openButton.textContent = 'Close camera scanner';
        if (!window.Html5QrcodeScanner) {
          setMessage('Camera scanner library did not load. Check your internet connection or use manual lookup.', 'error-text');
          return;
        }
        try {
          scanner = new Html5QrcodeScanner('reader', {
            fps: 10,
            qrbox: { width: 240, height: 180 },
            rememberLastUsedCamera: true,
            supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA]
          }, false);
          scanner.render(async decodedText => {
            scanInput.value = decodedText;
            await findProduct(decodedText);
            if (scanner) {
              scanner.clear().catch(() => {});
              scanner = null;
              reader.hidden = true;
              openButton.textContent = 'Open camera scanner';
            }
          }, () => {});
        } catch (error) {
          setMessage(`Unable to start camera: ${error.message}`, 'error-text');
        }
      } else {
        if (scanner) {
          try { await scanner.clear(); } catch (error) { /* camera may already be closed */ }
          scanner = null;
        }
        reader.hidden = true;
        openButton.textContent = 'Open camera scanner';
      }
    });
  }

  // For transfer forms, update stock when the source warehouse changes.
  const destination = document.getElementById('toWarehouse');
  if (destination) destination.addEventListener('change', () => {
    const source = document.getElementById('fromWarehouse');
    if (source.value && source.value === destination.value) {
      setMessage('Choose two different warehouses for a transfer.', 'error-text');
    }
  });
});
