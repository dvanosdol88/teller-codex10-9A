const STORE_KEY = 'teller:enrollment';
const SNAPSHOT_KEY = 'teller:dashboard-snapshot';
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

function getStoredSnapshot() {
  const raw = localStorage.getItem(SNAPSHOT_KEY);
  if (!raw) return null;
  try {
    const snapshot = JSON.parse(raw);
    if (!snapshot || typeof snapshot !== 'object') return null;
    return snapshot;
  } catch (error) {
    console.warn('Failed to parse stored dashboard snapshot', error);
    return null;
  }
}

function storeSnapshot(snapshot) {
  try {
    localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
  } catch (error) {
    console.warn('Unable to persist dashboard snapshot', error);
  }
}

function clearSnapshot() {
  localStorage.removeItem(SNAPSHOT_KEY);
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
    this.snapshot = getStoredSnapshot();
    this.currentUser = this.snapshot?.user ?? null;
  }

  init() {
    if (this.statusEnvironment) {
      this.statusEnvironment.textContent = this.config.environment;
    }
    const enrollment = getStoredEnrollment();
    if (enrollment?.accessToken) {
      this.onConnected(enrollment);
      this.bootstrap();
    } else if (this.snapshot && Object.values(this.snapshot.accounts ?? {}).length) {
      this.renderSnapshot(this.snapshot);
      this.onDisconnected({ preserveCards: true });
    } else {
      setHidden(this.emptyState, false);
    }
    this.setupConnect();
  }

  renderSnapshot(snapshot) {
    if (!snapshot || !this.grid) return;
    this.grid.innerHTML = '';
    this.cards.clear();
    const accounts = Object.values(snapshot.accounts ?? {});
    if (!accounts.length) {
      setHidden(this.emptyState, false);
      return;
    }
    setHidden(this.emptyState, true);
    accounts.forEach((entry) => {
      if (!entry?.summary) return;
      this.renderCard(entry.summary, {
        offline: true,
        balance: entry.balance,
        transactions: entry.transactions,
      });
    });
    this.toggleCardInteractivity(false);
  }

  prepareSnapshot(accounts) {
    const nextSnapshot = {
      accounts: {},
      lastUpdated: new Date().toISOString(),
      user: this.currentUser,
    };
    const previous = this.snapshot?.accounts ?? {};
    accounts.forEach((account) => {
      const existing = previous[account.id] || {};
      nextSnapshot.accounts[account.id] = {
        summary: account,
        balance: existing.balance ?? null,
        transactions: existing.transactions ?? null,
      };
    });
    this.snapshot = nextSnapshot;
    storeSnapshot(this.snapshot);
  }

  updateSnapshot(accountId, payload) {
    if (!accountId) return;
    if (!this.snapshot) {
      this.snapshot = { accounts: {}, lastUpdated: null, user: this.currentUser };
    }
    if (!this.snapshot.accounts) {
      this.snapshot.accounts = {};
    }
    const existing = this.snapshot.accounts[accountId] || {};
    this.snapshot.accounts[accountId] = {
      summary: payload.summary ?? existing.summary ?? null,
      balance: payload.balance ?? existing.balance ?? null,
      transactions: payload.transactions ?? existing.transactions ?? null,
    };
    this.snapshot.lastUpdated = new Date().toISOString();
    if (this.currentUser) {
      this.snapshot.user = this.currentUser;
    }
    storeSnapshot(this.snapshot);
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
      this.prepareSnapshot(accounts);
      if (!accounts.length) {
        setHidden(this.emptyState, false);
        return;
      }
      accounts.forEach((account) => {
        const cached = this.snapshot?.accounts?.[account.id];
        this.renderCard(account, {
          balance: cached?.balance ?? null,
          transactions: cached?.transactions ?? null,
        });
      });
      this.toggleCardInteractivity(this.connected);
    } catch (error) {
      if (error.status === 401) {
        clearEnrollment();
        this.reset();
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
    this.currentUser = {
      id: enrollment.user?.id ?? null,
      name: enrollment.user?.name ?? null,
    };
    if (this.snapshot) {
      this.snapshot.user = this.currentUser;
      storeSnapshot(this.snapshot);
    }
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
    const hasSnapshot = this.snapshot && Object.values(this.snapshot.accounts ?? {}).length;
    if (hasSnapshot) {
      this.renderSnapshot(this.snapshot);
      this.onDisconnected({ preserveCards: true });
    } else {
      this.onDisconnected({ preserveCards: false });
    }
  }

  renderCard(account, options = {}) {
    if (!this.template) return;
    const { offline = false, balance: initialBalance = null, transactions: initialTransactions = null } = options;
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
    this.populateCard(account.id, account, {
      offline,
      balance: initialBalance,
      transactions: initialTransactions,
    });
  }

  async populateCard(accountId, accountSummary, options = {}) {
    const card = this.cards.get(accountId);
    if (!card) return;
    const { offline = false, balance: providedBalance = null, transactions: providedTransactions = null } = options;
    const currency = accountSummary?.currency ?? 'USD';
    const nameEls = card.querySelectorAll('.account-name');
    nameEls.forEach((el) => (el.textContent = accountSummary?.name ?? 'Account'));
    const subtitle = [accountSummary?.institution, accountSummary?.last_four ? `•••• ${accountSummary.last_four}` : null]
      .filter(Boolean)
      .join(' · ');
    card.querySelectorAll('.account-subtitle').forEach((el) => (el.textContent = subtitle));

    const availableEl = card.querySelector('.balance-available');
    const ledgerEl = card.querySelector('.balance-ledger');
    const cachedBalanceEl = card.querySelector('.balance-cached');
    const applyBalance = (payload) => {
      const balanceData = payload?.balance ?? {};
      const cachedAt = payload?.cached_at ?? null;
      if (availableEl) availableEl.textContent = formatCurrency(balanceData.available, currency);
      if (ledgerEl) ledgerEl.textContent = formatCurrency(balanceData.ledger, currency);
      if (cachedBalanceEl) cachedBalanceEl.textContent = formatTimestamp(cachedAt);
    };

    let latestBalance = null;
    if (providedBalance) {
      applyBalance(providedBalance);
      latestBalance = providedBalance;
    }

    if (!offline) {
      try {
        const balance = await apiRequest(`/db/accounts/${accountId}/balances`);
        applyBalance(balance);
        latestBalance = balance;
      } catch (error) {
        console.warn('No cached balance yet', error);
        if (cachedBalanceEl) cachedBalanceEl.textContent = 'Never';
      }
    } else if (!providedBalance) {
      applyBalance(null);
    }

    const list = card.querySelector('.transactions-list');
    const emptyEl = card.querySelector('.transactions-empty');
    const cachedTxEl = card.querySelector('.transactions-cached');
    const applyTransactions = (payload) => {
      if (list) list.innerHTML = '';
      const txs = payload?.transactions ?? [];
      if (!txs.length) {
        if (emptyEl) {
          emptyEl.textContent = 'No cached transactions yet.';
          setHidden(emptyEl, false);
        }
      } else {
        if (emptyEl) setHidden(emptyEl, true);
        txs.forEach((tx) => {
          if (!list) return;
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
      const cached = payload?.cached_at ? formatTimestamp(payload.cached_at) : 'Never';
      if (cachedTxEl) cachedTxEl.textContent = `Cached: ${cached}`;
    };

    let latestTransactions = null;
    if (providedTransactions) {
      applyTransactions(providedTransactions);
      latestTransactions = providedTransactions;
    }

    if (!offline) {
      try {
        const transactions = await apiRequest(`/db/accounts/${accountId}/transactions`, {
          params: { limit: MAX_TRANSACTIONS },
        });
        applyTransactions(transactions);
        latestTransactions = transactions;
      } catch (error) {
        console.warn('No cached transactions yet', error);
        if (emptyEl) {
          emptyEl.textContent = 'Unable to load transactions.';
          setHidden(emptyEl, false);
        }
        if (cachedTxEl) cachedTxEl.textContent = 'Cached: Never';
      }
    } else if (!providedTransactions) {
      applyTransactions(null);
    }

    this.updateSnapshot(accountId, {
      summary: accountSummary,
      balance: latestBalance,
      transactions: latestTransactions,
    });
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
