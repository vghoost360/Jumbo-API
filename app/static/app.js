/* ── Jumbo API Dashboard ──────────────────────────────── */
try { fetch("/api/health?debug=js_start"); } catch(e) {}

// ── Navigation ──────────────────────────────────────────
const panelTitles = {
  basket: "Shopping Basket",
  lists: "Shopping Lists",
  orders: "Orders & Receipts",
  actions: "Quick Actions",
  history: "Command History",
  docs: "API Documentation",
  settings: "Settings",
};

document.querySelectorAll(".nav-item").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    const target = link.dataset.panel;

    document.querySelectorAll(".nav-item").forEach((l) => l.classList.remove("active"));
    link.classList.add("active");

    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    document.getElementById(`panel-${target}`).classList.add("active");

    document.getElementById("page-title").textContent = panelTitles[target] || "";

    if (target === "basket") refreshBasket();
    if (target === "lists") loadLists();
    if (target === "orders") loadOrders();
    if (target === "history") loadHistory();
    if (target === "settings") loadSettings();
  });
});
try { fetch("/api/health?debug=after_nav"); } catch(e) {}

// ── Auth ────────────────────────────────────────────────
function showLoginModal() {
  document.getElementById("login-modal").classList.add("show");
  document.getElementById("login-username").focus();
}

function hideLoginModal() {
  document.getElementById("login-modal").classList.remove("show");
  document.getElementById("login-status").textContent = "";
}

async function submitLogin() {
  const user = document.getElementById("login-username").value.trim();
  const pass = document.getElementById("login-password").value;
  if (!user || !pass) return;

  const btn = document.getElementById("submit-login-btn");
  const status = document.getElementById("login-status");

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Logging in…';
  status.className = "login-status";
  status.textContent = "Automated login in progress (~8s)…";

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: user, password: pass }),
    });
    const data = await res.json();

    if (data.success) {
      status.textContent = `Authenticated (${data.cookies_captured} cookies)`;
      status.className = "login-status success";
      toast("Login successful", "success");
      setTimeout(() => { hideLoginModal(); checkAuth(); refreshBasket(); }, 800);
    } else {
      status.textContent = data.message || "Login failed";
      status.className = "login-status error";
      toast(data.message || "Login failed", "error");
    }
  } catch (err) {
    status.textContent = "Network error";
    status.className = "login-status error";
    toast("Login request failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Login";
  }
}

async function checkAuth() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    const dot = document.getElementById("auth-dot");
    const txt = document.getElementById("auth-text");
    const btn = document.getElementById("login-btn");

    console.log("Auth status:", data);

    if (data.authenticated) {
      dot.className = "auth-dot online";
      txt.textContent = "Connected";
      btn.textContent = "Reconnect";
    } else if (data.has_credentials && data.auto_reauth_enabled) {
      dot.className = "auth-dot reconnecting";
      txt.textContent = "Reconnecting...";
      btn.textContent = "Login";
      // Trigger a basket refresh to force re-auth
      setTimeout(() => refreshBasket().then(() => checkAuth()), 2000);
    } else {
      dot.className = "auth-dot offline";
      txt.textContent = "Offline";
      btn.textContent = "Login";
    }
  } catch (err) {
    console.error("Auth check failed:", err);
  }
}

// ── Basket ──────────────────────────────────────────────
async function refreshBasket() {
  const container = document.getElementById("basket-content");
  const countEl = document.getElementById("basket-count");
  const totalEl = document.getElementById("basket-total");

  try {
    const res = await fetch("/api/basket");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to load basket");
    }
    const basket = await res.json();
    const lines = basket.lines || [];

    countEl.textContent = lines.length;

    // Calculate total
    let total = 0;
    lines.forEach((l) => {
      const p = l.details?.price?.price;
      if (p) total += (p / 100) * l.quantity;
    });
    totalEl.textContent = `€${total.toFixed(2)}`;

    if (lines.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>Your basket is empty</p></div>';
      return;
    }

    container.innerHTML = lines
      .map((line) => {
        const d = line.details || {};
        const price = d.price?.price ? `€${(d.price.price / 100).toFixed(2)}` : "";
        const promo = d.price?.promoPrice ? `€${(d.price.promoPrice / 100).toFixed(2)}` : "";
        const img = d.image || "";
        const title = d.title || d.sku || line.sku;

        return `
          <div class="basket-item">
            ${img ? `<img class="basket-item-img" src="${img}" alt="" loading="lazy">` : ""}
            <div class="basket-item-info">
              <div class="basket-item-title">${esc(title)}</div>
              <div class="basket-item-meta">SKU ${esc(line.sku)}${d.brand ? " · " + esc(d.brand) : ""}</div>
            </div>
            <div class="basket-item-qty-controls">
              <button class="qty-btn" onclick="updateQuantity('${line.id}', ${Math.max(1, line.quantity - 1)})" title="Decrease quantity">−</button>
              <span class="qty-display">${line.quantity}</span>
              <button class="qty-btn" onclick="updateQuantity('${line.id}', ${line.quantity + 1})" title="Increase quantity">+</button>
            </div>
            <span class="basket-item-price">${promo || price}</span>
            <button class="basket-item-remove" onclick="removeLine('${line.id}','${esc(line.sku)}')" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>`;
      })
      .join("");
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
    countEl.textContent = "–";
    totalEl.textContent = "–";
  }
}

async function removeLine(lineId, sku) {
  try {
    const res = await fetch("/api/basket/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line_id: lineId }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Remove failed");
    toast(`Removed ${sku}`, "success");
    refreshBasket();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function updateQuantity(lineId, quantity) {
  try {
    const res = await fetch(`/api/basket/items/${lineId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Update failed");
    toast(`Updated quantity to ${quantity}`, "success");
    refreshBasket();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ── Lists ───────────────────────────────────────────────
async function loadLists() {
  const container = document.getElementById("lists-content");
  const countEl = document.getElementById("lists-count");
  const productsEl = document.getElementById("lists-products");

  try {
    const res = await fetch("/api/lists");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to load lists");
    }
    const data = await res.json();
    
    const customerLists = data.customerLists?.items || [];
    const favouriteLists = data.favouriteLists?.items || [];
    const allLists = [...customerLists, ...favouriteLists];

    countEl.textContent = customerLists.length;
    
    // Calculate total products
    let totalProducts = 0;
    allLists.forEach((list) => {
      totalProducts += list.productsCount || 0;
    });
    productsEl.textContent = totalProducts;

    if (allLists.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No lists found</p></div>';
      return;
    }

    // Group lists by type
    let html = '';
    
    if (favouriteLists.length > 0) {
      html += '<div class="lists-section"><h3 class="lists-section-title">⭐ Favorites</h3>';
      html += favouriteLists.map(list => renderListCard(list)).join('');
      html += '</div>';
    }
    
    if (customerLists.length > 0) {
      html += '<div class="lists-section"><h3 class="lists-section-title">📋 My Lists</h3>';
      html += customerLists.map(list => renderListCard(list)).join('');
      html += '</div>';
    }
    
    container.innerHTML = html;
  } catch (err) {
    console.error("Error loading lists:", err);
    container.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
    countEl.textContent = "–";
    productsEl.textContent = "–";
    toast(err.message, "error");
  }
}

function renderListCard(list) {
  const previewImages = (list.items || [])
    .slice(0, 4)
    .map(item => item.product?.image)
    .filter(img => img);
  
  const previewHtml = previewImages.length > 0
    ? previewImages.map(img => `<img src="${img}" alt="" loading="lazy">`).join('')
    : '<div class="list-card-empty-preview">No items</div>';

  return `
    <div class="list-card" onclick="openListDetail('${list.id}')">
      <div class="list-card-preview">
        ${previewHtml}
      </div>
      <div class="list-card-info">
        <div class="list-card-title">${esc(list.title)}</div>
        <div class="list-card-meta">
          ${list.productsCount || 0} product${list.productsCount === 1 ? '' : 's'}
          ${list.author?.name ? ' · ' + esc(list.author.name) : ''}
        </div>
        ${list.description ? `<div class="list-card-desc">${esc(list.description)}</div>` : ''}
      </div>
    </div>`;
}

// ── List Detail Modal ───────────────────────────────────
async function openListDetail(listId) {
  const modal = document.getElementById("list-detail-modal");
  const titleEl = document.getElementById("list-detail-title");
  const metaEl = document.getElementById("list-detail-meta");
  const contentEl = document.getElementById("list-detail-content");

  modal.classList.add("show");
  titleEl.textContent = "Loading...";
  metaEl.textContent = "";
  contentEl.innerHTML = '<div class="empty-state"><p>Loading list details...</p></div>';

  try {
    const res = await fetch(`/api/lists/${encodeURIComponent(listId)}`);
    if (!res.ok) {
      throw new Error((await res.json()).detail || "Failed to load list");
    }
    const list = await res.json();

    titleEl.textContent = list.title || "Unnamed List";
    metaEl.textContent = `${list.productsCount || 0} products${list.author?.name ? ' · ' + list.author.name : ''}`;

    const items = list.items || [];
    if (items.length === 0) {
      contentEl.innerHTML = '<div class="empty-state"><p>This list is empty</p></div>';
      return;
    }

    contentEl.innerHTML = items
      .map((item) => {
        const p = item.product || {};
        const price = p.prices?.price ? `€${(p.prices.price / 100).toFixed(2)}` : "";
        const promo = p.prices?.promoPrice ? `€${(p.prices.promoPrice / 100).toFixed(2)}` : "";
        const img = p.image || "";
        const title = p.title || p.sku || item.sku;
        const subtitle = p.subtitle || "";

        return `
          <div class="list-product-item">
            ${img ? `<img class="list-product-img" src="${img}" alt="" loading="lazy">` : ""}
            <div class="list-product-info">
              <div class="list-product-title">${esc(title)}</div>
              <div class="list-product-meta">
                ${subtitle ? esc(subtitle) + " · " : ""}SKU ${esc(item.sku)}${p.brand ? " · " + esc(p.brand) : ""}
              </div>
            </div>
            <span class="list-product-price">
              ${promo ? `<span class="list-product-promo">${price}</span>${promo}` : price}
            </span>
          </div>`;
      })
      .join("");
  } catch (err) {
    contentEl.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
    toast(err.message, "error");
  }
}

function hideListDetailModal() {
  document.getElementById("list-detail-modal").classList.remove("show");
}

// ── Orders ──────────────────────────────────────────────
async function loadOrders() {
  const ordersContainer = document.getElementById("orders-content");
  const receiptsContainer = document.getElementById("receipts-content");
  const ordersCountEl = document.getElementById("orders-count");
  const receiptsCountEl = document.getElementById("receipts-count");

  try {
    const res = await fetch("/api/orders?limit=10&page=0&page_size=10");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to load orders");
    }
    const data = await res.json();
    const orders = data.onlineOrders?.orders || [];
    const receipts = data.storeReceipts?.receipts || [];

    ordersCountEl.textContent = data.onlineOrders?.totalCount || 0;
    receiptsCountEl.textContent = data.storeReceipts?.totalResults || 0;

    if (orders.length === 0) {
      ordersContainer.innerHTML = '<div class="empty-state"><p>No online orders found</p></div>';
    } else {
      ordersContainer.innerHTML = orders.map(order => renderOrderCard(order)).join("");
    }

    if (receipts.length === 0) {
      receiptsContainer.innerHTML = '<div class="empty-state"><p>No store receipts found</p></div>';
    } else {
      receiptsContainer.innerHTML = receipts.map(receipt => renderReceiptCard(receipt)).join("");
    }
  } catch (err) {
    ordersContainer.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
    receiptsContainer.innerHTML = '';
    ordersCountEl.textContent = "–";
    receiptsCountEl.textContent = "–";
  }
}

function renderOrderCard(order) {
  const deliveryDate = new Date(order.deliveryDate);
  const dateStr = deliveryDate.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
  const amount = parseFloat(order.totalToPayMoneyType?.amount || 0).toFixed(2);
  const address = order.deliveryAddress;
  const addressStr = address ? `${address.street} ${address.houseNumber}${address.addition || ''}, ${address.city}` : '';
  
  const statusBadge = order.status === 'COMPLETED' ? 
    '<span class="order-status-badge completed">✓ Completed</span>' : 
    `<span class="order-status-badge">${order.status}</span>`;
  
  const typeLabel = order.fulfilmentType === 'HOME_DELIVERY' ? '🚚 Home Delivery' : '🏪 Collection';

  return `
    <div class="order-card" onclick="openOrderDetail('${order.orderId}')">
      <div class="order-card-header">
        <div>
          <div class="order-card-title">Order #${order.orderId}</div>
          <div class="order-card-meta">${dateStr} · ${typeLabel}</div>
        </div>
        ${statusBadge}
      </div>
      <div class="order-card-body">
        <div class="order-card-address">${esc(addressStr)}</div>
        <div class="order-card-amount">€${amount}</div>
      </div>
    </div>`;
}

function renderReceiptCard(receipt) {
  const purchaseDate = new Date(receipt.purchaseEndOn);
  const dateStr = purchaseDate.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
  const timeStr = purchaseDate.toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' });
  
  const storeName = receipt.store?.name || 'Online Order';
  const sourceLabel = receipt.receiptSource === 'ONLINE' ? '🛒 Online' : '🏪 In-store';
  const pointsStr = receipt.pointBalance ? `${receipt.pointBalance > 0 ? '+' : ''}${receipt.pointBalance} pts` : '';

  // Online receipts link to order detail; store receipts open receipt detail
  const isOnline = receipt.receiptSource === 'ONLINE';
  const txId = receipt.transactionId || '';
  const orderIdMatch = isOnline ? txId.match(/^(\d+)-/) : null;
  const clickAction = isOnline && orderIdMatch
    ? `openOrderDetail('${orderIdMatch[1]}')`
    : `openReceiptDetail('${txId}')`;

  return `
    <div class="receipt-card" onclick="${clickAction}">
      <div class="receipt-card-header">
        <div>
          <div class="receipt-card-title">${esc(storeName)}</div>
          <div class="receipt-card-meta">${dateStr} ${timeStr} · ${sourceLabel}</div>
        </div>
        ${pointsStr ? `<span class="receipt-points">${pointsStr}</span>` : ''}
      </div>
    </div>`;
}

function openOrderDetail(orderId) {
  const modal = document.getElementById("order-detail-modal");
  const titleEl = document.getElementById("order-detail-title");
  const metaEl = document.getElementById("order-detail-meta");
  const contentEl = document.getElementById("order-detail-content");

  modal.classList.add("show");
  titleEl.textContent = `Order #${orderId}`;
  metaEl.textContent = "Loading...";
  contentEl.innerHTML = '<div class="empty-state"><p>Loading order details...</p></div>';

  fetch(`/api/orders/${orderId}`)
    .then(res => {
      if (!res.ok) throw new Error("Failed to load order");
      return res.json();
    })
    .then(order => {
      // Extract order info
      const status = order.progress?.status || "UNKNOWN";
      const deliveryDate = order.deliveryDate ? new Date(order.deliveryDate).toLocaleDateString("nl-NL") : "";
      const total = order.totals?.totalToPay?.amount || "0.00";
      const itemsCount = order.items?.length || 0;
      const fulfilmentType = order.fulfilmentType === "HOME_DELIVERY" ? "Home Delivery" : "Store Pickup";
      
      // Update meta info
      metaEl.textContent = `${fulfilmentType} · ${deliveryDate} · ${itemsCount} items · Total: €${total}`;

      // Render items
      const items = order.items || [];
      if (items.length === 0) {
        contentEl.innerHTML = '<div class="empty-state"><p>No items in this order</p></div>';
        return;
      }

      contentEl.innerHTML = items
        .map(item => {
          const details = item.details || {};
          const img = details.image || "";
          const title = details.title || item.sku;
          const subtitle = details.subtitle || "";
          const brand = details.brand || "";
          const qty = item.quantity || 0;
          const orderedQty = item.orderedQuantity || 0;
          const price = item.linePriceIncDiscount?.amount || "0.00";
          
          // Check if item was substituted or not delivered
          const isSubstitute = item.substitution?.substituteFor;
          const notDelivered = orderedQty > 0 && qty === 0;
          const substitutedBy = item.substitution?.substitutedBy || [];
          
          let statusBadge = "";
          if (isSubstitute) {
            statusBadge = '<span class="order-item-badge order-item-badge-substitute">Substitute</span>';
          } else if (notDelivered) {
            statusBadge = '<span class="order-item-badge order-item-badge-unavailable">Not Delivered</span>';
          } else if (substitutedBy.length > 0) {
            statusBadge = '<span class="order-item-badge order-item-badge-substituted">Substituted</span>';
          }
          
          return `
            <div class="order-item ${notDelivered ? 'order-item-unavailable' : ''}">
              ${img ? `<img class="order-item-img" src="${img}" alt="" loading="lazy">` : ""}
              <div class="order-item-info">
                <div class="order-item-title">${esc(title)} ${statusBadge}</div>
                <div class="order-item-meta">
                  ${subtitle ? esc(subtitle) + " · " : ""}${brand ? esc(brand) + " · " : ""}SKU ${esc(item.sku)}
                </div>
                ${orderedQty !== qty ? `<div class="order-item-qty-note">Ordered: ${orderedQty}, Delivered: ${qty}</div>` : ""}
                ${substitutedBy.length > 0 ? `<div class="order-item-substitute-note">Substituted by: ${substitutedBy.join(", ")}</div>` : ""}
              </div>
              <div class="order-item-right">
                <span class="order-item-qty">×${qty}</span>
                <span class="order-item-price">€${price}</span>
              </div>
            </div>`;
        })
        .join("");
    })
    .catch(err => {
      contentEl.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
      toast(err.message, "error");
    });
}

function hideOrderDetailModal() {
  document.getElementById("order-detail-modal").classList.remove("show");
}

function openReceiptDetail(transactionId) {
  const modal = document.getElementById("receipt-detail-modal");
  const titleEl = document.getElementById("receipt-detail-title");
  const metaEl = document.getElementById("receipt-detail-meta");
  const contentEl = document.getElementById("receipt-detail-content");

  modal.classList.add("show");
  titleEl.textContent = "Store Receipt";
  metaEl.textContent = "Loading...";
  contentEl.innerHTML = '<div class="empty-state"><p>Loading receipt details...</p></div>';

  fetch(`/api/receipts/${encodeURIComponent(transactionId)}`)
    .then(res => {
      if (!res.ok) throw new Error("Failed to load receipt");
      return res.json();
    })
    .then(receipt => {
      const storeName = receipt.store?.name || "Unknown Store";
      const storeAddr = receipt.store?.location?.address;
      const addrStr = storeAddr
        ? `${storeAddr.street} ${storeAddr.houseNumber}, ${storeAddr.postalCode} ${storeAddr.city}`
        : "";
      const date = receipt.purchaseEndOn
        ? new Date(receipt.purchaseEndOn).toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" })
        : "";
      const time = receipt.purchaseEndOn
        ? new Date(receipt.purchaseEndOn).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })
        : "";
      const items = receipt.items || [];
      const deposits = receipt.deposits || [];
      const total = receipt.total;
      const points = receipt.points;
      const payment = receipt.paymentMethod;
      const vat = receipt.vatSummary || [];

      titleEl.textContent = storeName;
      const metaParts = [date, time, addrStr].filter(Boolean);
      if (receipt.itemCount) metaParts.push(`${receipt.itemCount} items`);
      if (total != null) metaParts.push(`Total: €${total.toFixed(2)}`);
      metaEl.textContent = metaParts.join(" · ");

      if (items.length === 0 && deposits.length === 0) {
        contentEl.innerHTML = '<div class="empty-state"><p>No items found in this receipt</p></div>';
        return;
      }

      let html = "";

      // Product items
      html += items.map(item => {
        const priceStr = item.price != null ? `€${item.price.toFixed(2)}` : "";
        const qtyInfo = item.quantity > 1
          ? `<span class="receipt-item-qty">${item.quantity} × €${(item.unitPrice || 0).toFixed(2)}</span>`
          : "";
        const promoTag = item.isPromo ? ' <span class="receipt-promo-tag">Promo</span>' : "";
        const conf = item.matchConfidence;
        const confClass = conf >= 70 ? "conf-high" : conf >= 40 ? "conf-med" : "conf-low";
        const confBadge = conf != null
          ? ` <span class="confidence-badge ${confClass}" title="Match confidence: ${conf}%">${conf}%</span>`
          : "";

        const hasProduct = item.sku != null;
        if (hasProduct) {
          // Enriched item – render like an order item with image, brand, SKU
          const img = item.image || "";
          const title = item.fullTitle || item.name;
          const subtitle = item.subtitle || "";
          const brand = item.brand || "";
          return `
            <div class="order-item receipt-enriched-item">
              ${img ? `<img class="order-item-img" src="${img}" alt="" loading="lazy">` : '<div class="order-item-img-placeholder"></div>'}
              <div class="order-item-info">
                <div class="order-item-title">${esc(title)}${promoTag}${confBadge}</div>
                <div class="order-item-meta">
                  ${subtitle ? esc(subtitle) + " · " : ""}${brand ? esc(brand) + " · " : ""}SKU ${esc(item.sku)}
                </div>
                ${qtyInfo}
              </div>
              <div class="order-item-right">
                ${item.quantity > 1 ? `<span class="order-item-qty">×${item.quantity}</span>` : ""}
                <span class="order-item-price">${priceStr}</span>
              </div>
            </div>`;
        }

        // Plain item – no catalog match found
        return `
          <div class="receipt-item">
            <div class="receipt-item-info">
              <div class="receipt-item-name">${esc(item.name)}${promoTag}${conf != null ? confBadge : ""}</div>
              ${qtyInfo}
            </div>
            <div class="receipt-item-price">${priceStr}</div>
          </div>`;
      }).join("");

      // Deposit items
      if (deposits.length > 0) {
        html += '<div class="receipt-section-label">Statiegeld (Deposit)</div>';
        html += deposits.map(dep => {
          const priceStr = dep.price != null ? `€${dep.price.toFixed(2)}` : "";
          const qtyInfo = dep.quantity > 1
            ? `<span class="receipt-item-qty">${dep.quantity} × €${(dep.unitPrice || 0).toFixed(2)}</span>`
            : "";
          return `
            <div class="receipt-item receipt-item-deposit">
              <div class="receipt-item-info">
                <div class="receipt-item-name">${esc(dep.name)}</div>
                ${qtyInfo}
              </div>
              <div class="receipt-item-price">${priceStr}</div>
            </div>`;
        }).join("");
      }

      // Total
      if (total != null) {
        html += `
          <div class="receipt-total-row">
            <span>Total</span>
            <span>€${total.toFixed(2)}</span>
          </div>`;
      }

      // Payment
      if (payment) {
        html += `<div class="receipt-payment">Paid with: ${esc(payment)}</div>`;
      }

      // VAT summary
      if (vat.length > 0) {
        html += '<div class="receipt-section-label">VAT Summary</div>';
        html += '<div class="receipt-vat-table">';
        html += '<div class="receipt-vat-row receipt-vat-header"><span>Rate</span><span>Excl.</span><span>VAT</span></div>';
        vat.forEach(v => {
          html += `<div class="receipt-vat-row"><span>${esc(v.rate)}</span><span>€${esc(v.amountExcl || "–")}</span><span>€${esc(v.vatAmount || "–")}</span></div>`;
        });
        html += '</div>';
      }

      // Points
      if (points) {
        html += '<div class="receipt-section-label">Jumbo Extra\'s Points</div>';
        html += '<div class="receipt-points-grid">';
        if (points.oldBalance != null) html += `<div class="receipt-points-item"><span class="receipt-points-label">Previous</span><span class="receipt-points-value">${points.oldBalance}</span></div>`;
        if (points.earned != null) html += `<div class="receipt-points-item"><span class="receipt-points-label">Earned</span><span class="receipt-points-value receipt-points-earned">+${points.earned}</span></div>`;
        if (points.redeemed != null) html += `<div class="receipt-points-item"><span class="receipt-points-label">Redeemed</span><span class="receipt-points-value receipt-points-redeemed">-${points.redeemed}</span></div>`;
        if (points.newBalance != null) html += `<div class="receipt-points-item"><span class="receipt-points-label">New Balance</span><span class="receipt-points-value receipt-points-balance">${points.newBalance}</span></div>`;
        html += '</div>';
      }

      contentEl.innerHTML = html;
    })
    .catch(err => {
      contentEl.innerHTML = `<div class="empty-state"><p>${esc(err.message)}</p></div>`;
      toast(err.message, "error");
    });
}

function hideReceiptDetailModal() {
  document.getElementById("receipt-detail-modal").classList.remove("show");
}

// ── Actions ─────────────────────────────────────────────
async function addProduct() {
  const sku = document.getElementById("add-sku").value.trim();
  const qty = parseFloat(document.getElementById("add-quantity").value) || 1;
  if (!sku) return toast("Enter a SKU", "error");

  try {
    const res = await fetch("/api/basket/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku, quantity: qty }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Add failed");
    toast(`Added ${sku}`, "success");
    document.getElementById("add-sku").value = "";
    refreshBasket();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function removeProduct() {
  const val = document.getElementById("remove-sku").value.trim();
  if (!val) return toast("Enter a SKU or Line ID", "error");

  const body = val.length > 20 ? { line_id: val } : { sku: val };

  try {
    const res = await fetch("/api/basket/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Remove failed");
    toast(`Removed ${val}`, "success");
    document.getElementById("remove-sku").value = "";
    refreshBasket();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function lookupBarcode() {
  const code = document.getElementById("barcode-input").value.trim();
  if (!code) return toast("Enter a barcode", "error");

  const box = document.getElementById("barcode-result");
  box.innerHTML = '<span class="spinner"></span> Looking up…';

  try {
    const res = await fetch("/api/products/barcode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ barcode: code }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Not found");
    const p = await res.json();
    const price = p.price?.price ? `€${(p.price.price / 100).toFixed(2)}` : "–";

    let result = `
      <div class="result-title">${esc(p.title)}</div>
      <div class="result-row">SKU: ${esc(p.sku)} · EAN: ${esc(p.ean)}</div>`;
    
    // Show OpenFoodFacts match info if applicable
    if (p.matchSource === 'OpenFoodFacts') {
      const scoreColor = p.eanMatchScore >= 90 ? 'var(--success)' : p.eanMatchScore >= 70 ? 'var(--warning)' : 'var(--danger)';
      result += `<div class="result-row" style="color:${scoreColor}">🔍 Found via OpenFoodFacts: "${esc(p.matchedName)}"</div>`;
      if (p.scannedBarcode && p.scannedBarcode !== p.ean) {
        result += `<div class="result-row" style="font-size:0.85em;">Scanned: ${esc(p.scannedBarcode)} → Matched: ${esc(p.ean)} (${p.eanMatchScore}% match)</div>`;
      }
      if (p.eanMatchScore < 90) {
        result += `<div class="result-row" style="color:var(--warning);font-size:0.85em;">⚠️ Low EAN confidence - verify this is the correct product</div>`;
      }
    }
    
    result += `<div class="result-row">Price: ${price}</div>`;
    box.innerHTML = result;
  } catch (err) {
    box.innerHTML = `<span style="color:var(--danger)">${esc(err.message)}</span>`;
  }
}

async function searchProduct() {
  const sku = document.getElementById("search-sku").value.trim();
  if (!sku) return toast("Enter a SKU", "error");

  const box = document.getElementById("search-result");
  box.innerHTML = '<span class="spinner"></span> Searching…';

  try {
    const res = await fetch(`/api/products/search?sku=${encodeURIComponent(sku)}`);
    if (!res.ok) throw new Error((await res.json()).detail || "Not found");
    const p = await res.json();
    const price = p.price?.price ? `€${(p.price.price / 100).toFixed(2)}` : "–";

    box.innerHTML = `
      <div class="result-title">${esc(p.title)}</div>
      <div class="result-row">SKU: ${esc(p.sku || p.id)} · Brand: ${esc(p.brand || "–")}</div>
      <div class="result-row">Price: ${price}</div>`;
  } catch (err) {
    box.innerHTML = `<span style="color:var(--danger)">${esc(err.message)}</span>`;
  }
}

// ── Settings ────────────────────────────────────────────
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const s = await res.json();
    
    // Receipt product matching
    document.getElementById("setting-matching-enabled").checked = s.productMatchingEnabled;
    document.getElementById("setting-strict").checked = s.strictMatching;
    document.getElementById("setting-threshold").value = s.confidenceThreshold;
    document.getElementById("threshold-label").textContent = s.confidenceThreshold;
    
    // Barcode lookup
    document.getElementById("setting-openfoodfacts").checked = s.useOpenFoodFactsFallback;
    document.getElementById("setting-max-candidates").value = s.maxProductCandidates || 15;
    document.getElementById("setting-quantity-search").checked = s.useQuantityInSearch !== false;
    document.getElementById("setting-brand-search").checked = s.useBrandInSearch || false;
    
    // EAN matching scores
    document.getElementById("setting-ean-10").value = s.eanScore10Plus || 90;
    document.getElementById("setting-ean-8").value = s.eanScore8Plus || 70;
    document.getElementById("setting-ean-6").value = s.eanScore6Plus || 50;
    document.getElementById("setting-ean-4").value = s.eanScore4Plus || 30;
    
    // Matching criteria
    document.getElementById("setting-price").checked = s.usePriceMatching;
    document.getElementById("setting-weight").checked = s.useWeightMatching;
    document.getElementById("setting-name").checked = s.useNameMatching;
    
    // Matching weights
    document.getElementById("setting-price-weight").value = s.priceMatchWeight || 40;
    document.getElementById("setting-weight-weight").value = s.weightMatchWeight || 30;
    document.getElementById("setting-name-weight").value = s.nameMatchWeight || 30;
    
    // Cache
    document.getElementById("setting-barcode-cache").checked = s.useBarcodeCache !== false;
    
    // Credentials
    const usernameInput = document.getElementById("setting-username");
    const credStatus = document.getElementById("credentials-status");
    const removeBtn = document.getElementById("remove-creds-btn");
    
    if (s.hasCredentials) {
      usernameInput.value = s.username || "";
      credStatus.textContent = `✓ Credentials saved for ${s.username}`;
      credStatus.style.color = "var(--success)";
      removeBtn.style.display = "inline-block";
    } else {
      usernameInput.value = "";
      credStatus.textContent = "No credentials saved";
      credStatus.style.color = "";
      removeBtn.style.display = "none";
    }
    document.getElementById("setting-password").value = "";
  } catch {
    toast("Failed to load settings", "error");
  }
}

function updateThresholdLabel(val) {
  document.getElementById("threshold-label").textContent = val;
}

function updateMaxCandidatesLabel(val) {
  document.getElementById("max-candidates-label").textContent = val;
}

async function saveSetting(key, value) {
  try {
    const res = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    if (!res.ok) throw new Error("Save failed");
    toast("Setting saved", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function saveCredentials() {
  const username = document.getElementById("setting-username").value.trim();
  const password = document.getElementById("setting-password").value;
  
  if (!username || !password) {
    toast("Please enter both email and password", "error");
    return;
  }
  
  try {
    const res = await fetch("/api/settings/credentials", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error("Save failed");
    const data = await res.json();
    toast(data.message, "success");
    loadSettings(); // Reload to show updated status
  } catch (err) {
    toast(err.message, "error");
  }
}

async function removeCredentials() {
  if (!confirm("Remove saved credentials? You'll need to login manually after the next session expires.")) {
    return;
  }
  
  try {
    const res = await fetch("/api/settings/credentials", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ removeCredentials: true }),
    });
    if (!res.ok) throw new Error("Remove failed");
    const data = await res.json();
    toast(data.message, "success");
    loadSettings(); // Reload to show updated status
  } catch (err) {
    toast(err.message, "error");
  }
}

async function clearMatchCache() {
  try {
    const res = await fetch("/api/settings/clear-cache", { method: "POST" });
    if (!res.ok) throw new Error("Clear failed");
    const data = await res.json();
    toast(data.message, "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

// ── 
// ── History ─────────────────────────────────────────────
async function loadHistory() {
  const container = document.getElementById("history-content");
  try {
    const res = await fetch("/api/history?limit=30");
    const data = await res.json();
    const items = (data.history || []).reverse();

    if (items.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No commands yet</p></div>';
      return;
    }

    container.innerHTML = items
      .map((h) => {
        const t = new Date(h.timestamp);
        const time = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return `
          <div class="history-row">
            <span class="history-time">${time}</span>
            <span class="history-cmd">${esc(h.command)}</span>
            <span class="history-badge ${h.status}">${h.status}</span>
          </div>`;
      })
      .join("");
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load history</p></div>';
  }
}

// ── Toast ───────────────────────────────────────────────
let toastTimer;
function toast(msg, type = "info") {
  const el = document.getElementById("notification");
  clearTimeout(toastTimer);
  el.textContent = msg;
  el.className = `toast toast-${type} show`;
  toastTimer = setTimeout(() => (el.className = "toast"), 3200);
}

// ── Util ────────────────────────────────────────────────
function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ── Init ────────────────────────────────────────────────
// Initial check with small delay to let API start up
setTimeout(() => {
  checkAuth();
  refreshBasket();
}, 500);

// Check more frequently during first 30 seconds (every 5s)
let checkCount = 0;
const earlyInterval = setInterval(() => {
  checkAuth();
  checkCount++;
  if (checkCount >= 6) { // After 30 seconds, stop frequent checks
    clearInterval(earlyInterval);
  }
}, 5000);

// Auto-refresh every 30 seconds after initial period
setInterval(() => {
  checkAuth();
  if (document.querySelector('#panel-basket.active')) refreshBasket();
}, 30000);

// Refresh when page becomes visible again
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    checkAuth();
    refreshBasket();
  }
});

// Enter key for login modal
document.getElementById("login-password").addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitLogin();
});
