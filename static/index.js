const STORE_KEY = 'teller:enrollment';
const MAX_TRANSACTIONS = 10;

const toastEl = document.getElementById('toast');

let runtimeConfig = null;

async function fetchRuntimeConfig() {
  const response = await fetch('/api/config', { credentials: 'same-origin' });
  if (!response.ok) {
    throw new Error(`Failed to load runtime configuration: ${response.status}`);
  }
  const payload = await response.json();
  if (!payload || typeof payload !== 'object') {
    throw new Error('Runtime configuration payload was empty.');
  }
  const applicationId = typeof payload.applicationId === 'string' ? payload.applicationId.trim() : '';
  const environment = typeof payload.environment === 'string' ? payload.environment : 'development';
  const apiBaseUrl = typeof payload.apiBaseUrl === 'string' && payload.apiBaseUrl ? payload.apiBaseUrl : '/api';
  if (!applicationId) {
    throw new Error('Runtime configuration is missing applicationId.');
  }
  runtimeConfig = { applicationId, environment, apiBaseUrl };
  window.__tellerRuntimeConfig = runtimeConfig;
  return runtimeConfig;
}

function showToast(message, variant = 'info') {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.dataset.variant = variant;
  toastEl.classList.remove('hidden');
  requestAnimationFrame(() => toastEl.classList.add('visible'));
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toastEl.classList.remove('visible');
    setTimeout(() => toastEl.classList.add('hidden'), 300);
  }, 3200);
}

function setHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle('hidden', hidden);
}

function formatCurrency(amount, currency = 'USD') {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) {
    return '—';
  }
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(amount));
  } catch {
    return `${amount}`;
  }
}

function formatTimestamp(value) {
  if (!value) return 'Never';
  try {
    const date = typeof value === 'string' ? new Date(value) : value;
    if (Number.isNaN(date.getTime())) return 'Never';
    return date.toLocaleString();
  } catch {
    return 'Never';
  }
}

function formatAmount(amount, currency = 'USD') {
  if (amount === null || amount === undefined) return '—';
  const formatted = formatCurrency(Math.abs(Number(amount)), currency);
  return Number(amount) >= 0 ? `+${formatted}` : `-${formatted}`;
}

function getStoredEnrollment() {
  const raw = localStorage.getItem(STORE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.warn('Failed to parse stored enrollment', error);
    return null;
  }
}

function storeEnrollment(enrollment) {
  localStorage.setItem(STORE_KEY, JSON.stringify(enrollment));
}

function clearEnrollment() {
  localStorage.removeItem(STORE_KEY);
}

async function apiRequest(path, { method = 'GET', body, headers = {}, params } = {}) {
  const token = window.__tellerAccessToken;
  if (!token) throw new Error('Missing access token');
  const baseUrl = runtimeConfig?.apiBaseUrl || '/api';
  const finalHeaders = {
    Authorization: `Bearer ${token}`,
    ...headers,
  };
  const options = { method, headers: finalHeaders };
  if (body !== undefined) {
    options.body = typeof body === 'string' ? body : JSON.stringify(body);
    if (!('Content-Type' in finalHeaders)) {
      options.headers['Content-Type'] = 'application/json';
    }
  }
  if (params) { options.params = params; }
  const response = await fetch(`${baseUrl}${path}`, options);
  if (!response.ok) {
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = await response.text();
    }
    const error = new Error(`Request failed: ${response.status}`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

class Dashboard {
  constructor(config) {
    this.config = config;
    this.grid = document.getElementById('accounts-grid');
    this.emptyState = document.getElementById('empty-state');
    this.statusEnvironment = document.getElementById('status-environment');
    this.statusUser = document.getElementById('status-user');
    this.statusToken = document.getElementById('status-token');
    this.template = document.getElementById('account-card-template');
    this.cards = new Map();
    this.connected = false;
  }

  init() {
    if (this.statusEnvironment) {
      this.statusEnvironment.textContent = this.config.environment;
    }
    const enrollment = getStoredEnrollment();
    if (enrollment?.accessToken) {
      this.onConnected(enrollment);
      this.bootstrap();
    } else {
      setHidden(this.emptyState, false);
    }
    this.setupConnect();
  }

  setupConnect() {
    const connectBtn = document.getElementById('connect-btn');
    const disconnectBtn = document.getElementById('disconnect-btn');
    const { applicationId, environment } = this.config;
    if (!applicationId || !environment) {
      console.error('Runtime configuration is missing required Teller Connect values.');
      connectBtn?.setAttribute('disabled', 'true');
      return;
    }
    const connector = window.TellerConnect.setup({
      applicationId,
      environment,
      onSuccess: async (enrollment) => {
        try {
          window.__tellerAccessToken = enrollment.accessToken;
          storeEnrollment(enrollment);
          this.onConnected(enrollment);
          await apiRequest('/enrollments', {
            method: 'POST',
            body: { enrollment },
          });
          await this.bootstrap();
          showToast('Enrollment saved and cache primed.');
        } catch (error) {
          console.error(error);
          showToast('Unable to store enrollment. Please try again.', 'error');
        }
      },
      onExit: ({ error }) => {
        if (error) {
          console.error('Teller Connect error', error);
          showToast('Teller Connect exited with an error.', 'error');
        }
      },
    });

    connectBtn?.addEventListener('click', () => connector.open());
    disconnectBtn?.addEventListener('click', () => {
      clearEnrollment();
      window.__tellerAccessToken = undefined;
      this.onDisconnected({ preserveCards: true });
      connectBtn?.focus();
      if (disconnectBtn) disconnectBtn.hidden = true;
      showToast('Disconnected. Cached data remains available.');
    });
  }

  async bootstrap() {
    try {
      setHidden(this.emptyState, true);
      if (this.grid) {
        this.grid.innerHTML = '';
      }
      this.cards.clear();
      const data = await apiRequest('/db/accounts');
      const accounts = data?.accounts ?? [];
      if (!accounts.length) {
        setHidden(this.emptyState, false);
        return;
      }
      accounts.forEach((account) => this.renderCard(account));
      this.toggleCardInteractivity(this.connected);
    } catch (error) {
      if (error.status === 401) {
        this.reset();
        clearEnrollment();
        showToast('Session expired. Please reconnect.', 'error');
      } else {
        console.error('Failed to load accounts', error);
        showToast('Unable to load cached accounts.', 'error');
      }
    }
  }

  onConnected(enrollment) {
    window.__tellerAccessToken = enrollment.accessToken;
    this.connected = true;
    if (this.statusUser) {
      this.statusUser.textContent = enrollment.user?.id ?? 'Connected';
    }
    if (this.statusToken) {
      this.statusToken.textContent = enrollment.accessToken ?? '—';
    }
    if (this.statusEnvironment) {
      this.statusEnvironment.textContent = this.config.environment;
    }
    const disconnect = document.getElementById('disconnect-btn');
    if (disconnect) disconnect.hidden = false;
    setHidden(this.emptyState, true);
    this.toggleCardInteractivity(true);
  }

  onDisconnected({ preserveCards = false } = {}) {
    this.connected = false;
    if (this.statusUser) {
      this.statusUser.textContent = preserveCards ? 'Disconnected' : 'Not connected';
    }
    if (this.statusToken) {
      this.statusToken.textContent = '—';
    }
    if (this.statusEnvironment) {
      this.statusEnvironment.textContent = this.config.environment;
    }
    if (!preserveCards && this.grid) {
      this.grid.innerHTML = '';
    }
    if (!preserveCards) {
      this.cards.clear();
    }
    if (!preserveCards) {
      setHidden(this.emptyState, false);
    }
    this.toggleCardInteractivity(false);
  }

  reset() {
    this.onDisconnected({ preserveCards: false });
  }

  renderCard(account) {
    if (!this.template) return;
    const node = this.template.content.firstElementChild.cloneNode(true);
    node.dataset.accountId = account.id;
    const flipButtons = node.querySelectorAll('.flip-btn');
    flipButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        node.classList.toggle('is-flipped');
      });
    });

    const refreshBtn = node.querySelector('.refresh-btn');
    refreshBtn.addEventListener('click', async () => {
      if (!this.connected) {
        showToast('Connect to refresh this account.', 'info');
        return;
      }
      try {
        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Refreshing…';
        await Promise.all([
          apiRequest(`/accounts/${account.id}/balances`),
          apiRequest(`/accounts/${account.id}/transactions`, { params: { count: MAX_TRANSACTIONS } }),
        ]);
        await this.populateCard(account.id);
        showToast('Live data cached.');
      } catch (error) {
        console.error('Refresh failed', error);
        if (error.status === 401) {
          clearEnrollment();
          this.reset();
          showToast('Session expired. Please reconnect.', 'error');
        } else {
          showToast('Unable to refresh account.', 'error');
        }
      } finally {
        refreshBtn.disabled = !this.connected;
        refreshBtn.textContent = this.connected ? 'Refresh live' : 'Connect to refresh';
      }
    });

    if (this.grid) {
      this.grid.appendChild(node);
    }
    this.cards.set(account.id, node);
    refreshBtn.disabled = !this.connected;
    this.populateCard(account.id, account);
  }

  async populateCard(accountId, accountSummary) {
    const card = this.cards.get(accountId);
    if (!card) return;
    const currency = accountSummary?.currency ?? 'USD';
    const nameEls = card.querySelectorAll('.account-name');
    nameEls.forEach((el) => (el.textContent = accountSummary?.name ?? 'Account'));
    const subtitle = [accountSummary?.institution, accountSummary?.last_four ? `•••• ${accountSummary.last_four}` : null]
      .filter(Boolean)
      .join(' · ');
    card.querySelectorAll('.account-subtitle').forEach((el) => (el.textContent = subtitle));

    try {
      const balance = await apiRequest(`/db/accounts/${accountId}/balances`);
      const balanceData = balance?.balance ?? {};
      const cachedAt = balance?.cached_at ?? null;
      card.querySelector('.balance-available').textContent = formatCurrency(balanceData.available, currency);
      card.querySelector('.balance-ledger').textContent = formatCurrency(balanceData.ledger, currency);
      card.querySelector('.balance-cached').textContent = formatTimestamp(cachedAt);
    } catch (error) {
      console.warn('No cached balance yet', error);
      card.querySelector('.balance-cached').textContent = 'Never';
    }

    try {
      const transactions = await apiRequest(`/db/accounts/${accountId}/transactions`, {
        params: { limit: MAX_TRANSACTIONS },
      });
      const list = card.querySelector('.transactions-list');
      list.innerHTML = '';
      const txs = transactions?.transactions ?? [];
      if (!txs.length) {
        setHidden(card.querySelector('.transactions-empty'), false);
      } else {
        setHidden(card.querySelector('.transactions-empty'), true);
        txs.forEach((tx) => {
          const li = document.createElement('li');
          const details = document.createElement('div');
          details.className = 'details';
          const description = document.createElement('span');
          description.className = 'description';
          description.textContent = tx.description || 'Transaction';
          const date = document.createElement('span');
          date.className = 'date';
          date.textContent = tx.date ? new Date(tx.date).toLocaleDateString() : '';
          details.append(description, date);
          const amount = document.createElement('span');
          amount.className = 'amount';
          amount.textContent = formatAmount(tx.amount, currency);
          li.append(details, amount);
          list.appendChild(li);
        });
      }
      const cached = transactions?.cached_at ? formatTimestamp(transactions.cached_at) : 'Never';
      card.querySelector('.transactions-cached').textContent = `Cached: ${cached}`;
    } catch (error) {
      console.warn('No cached transactions yet', error);
      const empty = card.querySelector('.transactions-empty');
      empty.textContent = 'Unable to load transactions.';
      setHidden(empty, false);
    }
  }

  toggleCardInteractivity(isConnected) {
    this.cards.forEach((card) => {
      card.classList.toggle('is-disconnected', !isConnected);
      const refreshBtn = card.querySelector('.refresh-btn');
      if (refreshBtn) {
        refreshBtn.disabled = !isConnected;
        if (!isConnected) {
          refreshBtn.textContent = 'Connect to refresh';
        } else {
          refreshBtn.textContent = 'Refresh live';
        }
      }
    });
  }
}

(async function bootstrap() {
  patchFetchForParams();
  const connectBtn = document.getElementById('connect-btn');
  if (connectBtn) {
    connectBtn.setAttribute('disabled', 'true');
  }
  try {
    const config = await fetchRuntimeConfig();
    if (connectBtn) {
      connectBtn.removeAttribute('disabled');
    }
    const dashboard = new Dashboard(config);
    dashboard.init();
  } catch (error) {
    console.error('Failed to bootstrap dashboard', error);
    showToast('Unable to load configuration. Please try again later.', 'error');
  }
})();

function patchFetchForParams() {
  // Fetch wrapper to support query params via options.params for convenience.
  const originalFetch = window.fetch;
  window.fetch = (input, init = {}) => {
    if (init && init.params) {
      const url = new URL(typeof input === 'string' ? input : input.url, window.location.origin);
      Object.entries(init.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, value);
        }
      });
      delete init.params;
      return originalFetch(url.toString(), init);
    }
    return originalFetch(input, init);
  };
}
