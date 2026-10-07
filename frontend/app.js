/* ═══════════════════════════════════════════════════
   Hersheys E-Commerce Platform — Frontend App Logic
   Connects to Backend Microservices (Ports 8001, 8002, 8003)
   ═══════════════════════════════════════════════════ */

// Configuration for Backend Services
const CONFIG = {
  USER_SERVICE: 'http://k8s-ecommerc-ecommerc-7ba9b551d1-216629860.us-east-1.elb.amazonaws.com/api/v1',
  PRODUCT_SERVICE: 'http://k8s-ecommerc-ecommerc-7ba9b551d1-216629860.us-east-1.elb.amazonaws.com/api/v1',
  ORDER_SERVICE: 'http://k8s-ecommerc-ecommerc-7ba9b551d1-216629860.us-east-1.elb.amazonaws.com/api/v1'
};

// State
let state = {
  token: null, // JWT token for auth
  user: null,
  products: [],
  orders: [],
  users: []
};

// ── DOM Elements ──
const DOM = {
  navItems: document.querySelectorAll('.nav-item'),
  pages: document.querySelectorAll('.page'),
  toastContainer: document.getElementById('toast-container'),
  
  // Product Page
  productGrid: document.getElementById('product-grid'),
  addProductBtn: document.getElementById('add-product-btn'),
  modalProduct: document.getElementById('modal-product'),
  closeProductModal: document.getElementById('close-product-modal'),
  cancelProduct: document.getElementById('cancel-product'),
  saveProduct: document.getElementById('save-product'),
  
  // Orders Page
  ordersBody: document.getElementById('orders-body'),
  recentOrdersBody: document.getElementById('recent-orders-body'),
  
  // Users Page
  usersGrid: document.getElementById('users-grid'),
  
  // Health
  svcs: {
    user: document.getElementById('svc-user'),
    product: document.getElementById('svc-product'),
    order: document.getElementById('svc-order')
  }
};

// ── UTILITIES ──

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '❌';
  
  toast.innerHTML = `<span class="toast-icon">${icon}</span> <span>${message}</span>`;
  DOM.toastContainer.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'fadeIn 0.3s reverse forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount || 0);
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  return headers;
}

// ── API CALLS ──

async function apiCall(url, method = 'GET', data = null) {
  try {
    const options = {
      method,
      headers: getAuthHeaders(),
    };
    if (data) options.body = JSON.stringify(data);
    
    const response = await fetch(url, options);
    
    // For local dev, if fetch fails due to no backend, it throws error before this.
    // If response is not ok, parse error.
    if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error(`API Call failed for ${url}:`, error);
    throw error;
  }
}

// ── NAVIGATION LOGIC ──

DOM.navItems.forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    const pageId = item.getAttribute('data-page');
    if (!pageId) return;
    
    // Update active nav
    DOM.navItems.forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    
    // Update active page
    DOM.pages.forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${pageId}`).classList.add('active');
    
    // Load data for the page
    loadPageData(pageId);
  });
});

async function loadPageData(pageId) {
  try {
    if (pageId === 'dashboard') {
      await fetchDashboardData();
    } else if (pageId === 'products') {
      await fetchProducts();
    } else if (pageId === 'orders') {
      await fetchOrders();
    } else if (pageId === 'users') {
      await fetchUsers();
    } else if (pageId === 'services') {
      await checkServicesHealth();
    }
  } catch (err) {
    // Backend is likely not running yet
    showToast(`Could not load ${pageId} data (Backend might be down). Showing mock data.`, 'error');
    populateMockData(pageId);
  }
}

// ── FETCH DATA ──

async function fetchProducts() {
  const data = await apiCall(`${CONFIG.PRODUCT_SERVICE}/products/`);
  state.products = data.products || [];
  renderProducts();
}

async function fetchOrders() {
  // If no auth token, this might fail, using generic mock for now on error
  const data = await apiCall(`${CONFIG.ORDER_SERVICE}/orders/`);
  state.orders = data.orders || [];
  renderOrders();
}

async function fetchUsers() {
  const data = await apiCall(`${CONFIG.USER_SERVICE}/users/`);
  state.users = data.users || [];
  renderUsers();
}

async function fetchDashboardData() {
  await fetchProducts();
  await fetchOrders();
  // Compute dashboard metrics
  const revenue = state.orders.reduce((sum, order) => sum + (order.total_amount || 0), 0);
  document.querySelector('[data-count="84320"]').innerText = formatCurrency(revenue);
  document.querySelector('[data-count="1248"]').innerText = state.orders.length;
  document.querySelector('[data-count="142"]').innerText = state.products.length;
}

async function checkServicesHealth() {
  const services = [
    { el: DOM.svcs.user, url: 'http://localhost:8001/health' },
    { el: DOM.svcs.product, url: 'http://localhost:8002/health' },
    { el: DOM.svcs.order, url: 'http://localhost:8003/health' }
  ];

  for (const svc of services) {
    if(!svc.el) continue;
    const dot = svc.el.querySelector('.svc-status-dot');
    const statusText = svc.el.querySelector('.green-text');
    try {
      const res = await fetch(svc.url);
      if (res.ok) {
        dot.className = 'svc-status-dot green pulse';
        statusText.innerText = 'Healthy';
        statusText.className = 'green-text';
      } else {
        throw new Error('Degraded');
      }
    } catch (e) {
      dot.className = 'svc-status-dot';
      dot.style.background = '#ef4444';
      dot.style.boxShadow = '0 0 8px #ef4444';
      statusText.innerText = 'Offline';
      statusText.className = '';
      statusText.style.color = '#ef4444';
    }
  }
}

// ── RENDER DATA ──

function renderProducts() {
  if (state.products.length === 0) {
    DOM.productGrid.innerHTML = '<div class="card" style="grid-column: 1/-1; text-align: center; padding: 40px;">No products found. (Backend may be empty or offline)</div>';
    return;
  }
  
  DOM.productGrid.innerHTML = state.products.map(p => `
    <div class="product-card">
      <div class="product-img">${getCategoryIcon(p.category)}</div>
      <div class="product-body">
        <div class="product-brand">${p.brand || 'No Brand'}</div>
        <div class="product-name">${p.name}</div>
        <div class="product-stock">${p.stock_quantity} in stock • SKU: ${p.sku}</div>
        <div class="product-footer">
          <div class="product-price">${formatCurrency(p.price)}</div>
          <span class="badge ${p.status === 'active' ? 'green' : ''}">${p.status}</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderOrders() {
  const renderRows = (orders) => orders.map(o => `
    <tr>
      <td><strong>#${o.order_id.split('-')[0]}</strong></td>
      <td>User: ${o.user_id.substring(0,8)}...</td>
      <td>${o.items ? o.items.length : 0} items</td>
      <td><strong>${formatCurrency(o.total_amount)}</strong></td>
      <td><span class="status-badge sb-${o.order_status}">${o.order_status}</span></td>
      <td>${new Date(o.created_at).toLocaleDateString()}</td>
    </tr>
  `).join('');
  
  if (DOM.ordersBody) DOM.ordersBody.innerHTML = renderRows(state.orders);
  if (DOM.recentOrdersBody) DOM.recentOrdersBody.innerHTML = renderRows(state.orders.slice(0, 5));
}

function renderUsers() {
  if (state.users.length === 0) {
    DOM.usersGrid.innerHTML = '<div class="card" style="grid-column: 1/-1; text-align: center; padding: 40px;">No users found.</div>';
    return;
  }
  
  DOM.usersGrid.innerHTML = state.users.map(u => `
    <div class="user-card">
      <div class="user-card-header">
        <div class="user-avatar">${(u.first_name?.[0] || 'U')}${(u.last_name?.[0] || '')}</div>
        <div>
          <div class="user-info-name">${u.first_name} ${u.last_name}</div>
          <div class="user-info-email">${u.email}</div>
        </div>
      </div>
      <div class="user-meta">
        <span class="meta-chip">Role: ${u.role}</span>
        <span class="meta-chip">Status: ${u.status}</span>
      </div>
    </div>
  `).join('');
}

// Helper icons
function getCategoryIcon(cat) {
  const icons = { electronics: '💻', clothing: '👕', food: '🍔', books: '📚', home: '🏠', sports: '⚽' };
  return icons[cat?.toLowerCase()] || '📦';
}

// ── PRODUCT CREATION (Connected to Backend) ──
if (DOM.addProductBtn) {
  DOM.addProductBtn.addEventListener('click', () => {
    DOM.modalProduct.classList.add('open');
  });
}

[DOM.closeProductModal, DOM.cancelProduct].forEach(btn => {
  if(btn) btn.addEventListener('click', () => DOM.modalProduct.classList.remove('open'));
});

if (DOM.saveProduct) {
  DOM.saveProduct.addEventListener('click', async () => {
    const payload = {
      name: document.getElementById('p-name').value,
      sku: document.getElementById('p-sku').value,
      description: document.getElementById('p-desc').value,
      price: parseFloat(document.getElementById('p-price').value),
      stock_quantity: parseInt(document.getElementById('p-stock').value),
      category: document.getElementById('p-category').value.toLowerCase(),
      brand: document.getElementById('p-brand').value,
    };
    
    // Basic validation
    if (!payload.name || !payload.price) {
      showToast('Name and Price are required.', 'error');
      return;
    }
    
    try {
      DOM.saveProduct.innerText = 'Saving...';
      DOM.saveProduct.disabled = true;
      
      const newProduct = await apiCall(`${CONFIG.PRODUCT_SERVICE}/products/`, 'POST', payload);
      
      showToast(`Product ${newProduct.name} created successfully!`, 'success');
      DOM.modalProduct.classList.remove('open');
      
      // Reload products
      await fetchProducts();
    } catch (err) {
      showToast(`Failed to create product: ${err.message}`, 'error');
      // If backend is offline, just simulate it to unblock the UI
      if (err.message.includes("Failed to fetch")) {
        simulateProductCreation(payload);
      }
    } finally {
      DOM.saveProduct.innerText = 'Create Product →';
      DOM.saveProduct.disabled = false;
    }
  });
}

// ── MOCK DATA FALLBACK (If backend is offline) ──
function populateMockData(pageId) {
  if (pageId === 'products' && state.products.length === 0) {
    state.products = [
      { name: 'Sony WH-1000XM5', brand: 'Sony', category: 'electronics', price: 348.00, stock_quantity: 45, sku: 'SNY-WH5', status: 'active' },
      { name: 'MacBook Pro M3', brand: 'Apple', category: 'electronics', price: 1599.00, stock_quantity: 12, sku: 'APP-MBP14', status: 'active' },
      { name: 'Nike Air Force 1', brand: 'Nike', category: 'clothing', price: 110.00, stock_quantity: 80, sku: 'NKE-AF1', status: 'active' }
    ];
    renderProducts();
  }
  
  if ((pageId === 'orders' || pageId === 'dashboard') && state.orders.length === 0) {
    state.orders = [
      { order_id: 'ORD-1234-ABCD', user_id: 'USR-999', total_amount: 1599.00, order_status: 'confirmed', created_at: new Date().toISOString(), items: [1] },
      { order_id: 'ORD-5678-EFGH', user_id: 'USR-888', total_amount: 458.00, order_status: 'shipped', created_at: new Date(Date.now() - 86400000).toISOString(), items: [1, 2] }
    ];
    if (pageId === 'orders') renderOrders();
    if (pageId === 'dashboard') {
      document.querySelector('[data-count="84320"]').innerText = formatCurrency(2057);
      document.querySelector('[data-count="1248"]').innerText = 2;
      document.querySelector('[data-count="142"]').innerText = 3;
      renderOrders();
    }
  }
}

function simulateProductCreation(payload) {
  showToast('Backend offline. Simulated product creation locally.', 'info');
  state.products.unshift({
    ...payload,
    product_id: 'mock-' + Math.random().toString(36).substr(2, 9),
    status: 'active'
  });
  renderProducts();
  DOM.modalProduct.classList.remove('open');
}

// ── INIT ──
// Check services on load
checkServicesHealth();
// Load dashboard by default
loadPageData('dashboard');
