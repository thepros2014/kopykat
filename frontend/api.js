/**
 * api.js — Modern JavaScript API Client Wrapper for KopyKat.
 * Provides unified HTTP methods, authentication header injection, token caching, and error handling.
 */

class KopyKatAPI {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
  }

  getToken() {
    return localStorage.getItem('sc_token');
  }

  setToken(token) {
    if (token) {
      localStorage.setItem('sc_token', token);
    } else {
      localStorage.removeItem('sc_token');
    }
  }

  getHeaders(customHeaders = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...customHeaders
    };
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = this.getHeaders(options.headers || {});
    const config = {
      ...options,
      headers
    };

    if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
      config.body = JSON.stringify(config.body);
    }

    if (config.body instanceof FormData) {
      delete config.headers['Content-Type'];
    }

    try {
      const response = await fetch(url, config);

      if (response.status === 401) {
        // Clear session on unauthenticated and redirect
        localStorage.removeItem('sc_token');
        localStorage.removeItem('sc_user');
        if (window.location.pathname !== '/' && window.location.pathname !== '/login') {
          window.location.href = '/';
        }
      }

      const isJson = (response.headers.get('content-type') || '').includes('application/json');
      const data = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        let errorMsg = 'API request failed';
        if (typeof data === 'object' && data !== null) {
          errorMsg = data.detail || data.message || errorMsg;
          if (Array.isArray(errorMsg)) errorMsg = errorMsg[0].msg || errorMsg;
        } else if (typeof data === 'string') {
          errorMsg = data;
        }
        const error = new Error(errorMsg);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (err) {
      console.error(`[KopyKat API Error] ${options.method || 'GET'} ${endpoint}:`, err.message);
      throw err;
    }
  }

  // Convenience Methods
  get(endpoint, headers = {}) {
    return this.request(endpoint, { method: 'GET', headers });
  }

  post(endpoint, body, headers = {}) {
    return this.request(endpoint, { method: 'POST', body, headers });
  }

  delete(endpoint, headers = {}) {
    return this.request(endpoint, { method: 'DELETE', headers });
  }

  // Domain-specific Helpers
  getProfile() {
    return this.get('/auth/me');
  }

  getUsage() {
    return this.get('/api/usage');
  }

  getInventory() {
    return this.get('/api/inventory');
  }

  saveInventoryItem(sku, title, total_stock) {
    return this.post('/api/inventory/item', { sku, title, total_stock });
  }

  getPricingItems() {
    return this.get('/api/pricing/items');
  }

  savePricingItem(itemData) {
    return this.post('/api/pricing/item', itemData);
  }

  getReviews() {
    return this.get('/api/reviews');
  }

  generateUGCDrip(product_name, brand_tone, incentive_offer) {
    return this.post('/api/reviews/drip-templates', { product_name, brand_tone, incentive_offer });
  }

  getOpportunityLeads() {
    return this.get('/api/leads');
  }
}

// Global API instance
window.kopykat = new KopyKatAPI();
