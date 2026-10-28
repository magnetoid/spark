// Spark app glue: CSRF for htmx/fetch, toasts from HX-Trigger events,
// re-initialising Alpine + Basecoat after htmx swaps, and the composer modal hook.
(() => {
  const csrf = () => (document.querySelector('meta[name="csrf"]') || {}).content || '';

  // htmx: send the CSRF token on every non-GET request
  document.addEventListener('htmx:configRequest', (e) => {
    if (e.detail.verb && e.detail.verb.toLowerCase() !== 'get') e.detail.headers['X-CSRF-Token'] = csrf();
  });
  // fetch(): same-origin writes get the token too (composer.js, calendar drag, boards)
  const origFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const method = (init.method || 'GET').toUpperCase();
    const url = typeof input === 'string' ? input : input.url;
    if (method !== 'GET' && method !== 'HEAD' && (url.startsWith('/') || url.startsWith(location.origin))) {
      const headers = new Headers(init.headers || {});
      if (!headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', csrf());
      init = { ...init, headers };
    }
    return origFetch(input, init);
  };

  // Toasts (Basecoat toaster markup)
  window.toast = (message, kind = 'success', ms = 4000) => {
    const host = document.getElementById('toaster');
    if (!host) return;
    const el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-atomic', 'true');
    el.dataset.category = kind === 'error' ? 'error' : 'success';
    el.innerHTML = `<div class="toast-content"><section><h2>${escapeHtml(message)}</h2></section>
      <footer><button type="button" class="btn" data-variant="ghost" data-size="icon-xs" aria-label="Dismiss">×</button></footer></div>`;
    el.querySelector('button').onclick = () => el.remove();
    host.appendChild(el);
    requestAnimationFrame(() => el.setAttribute('aria-hidden', 'false'));
    setTimeout(() => { el.setAttribute('aria-hidden', 'true'); setTimeout(() => el.remove(), 400); }, ms);
  };
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  // Server-fired events: HX-Trigger: {"toast": {...}, "post-saved": {...}}
  document.body.addEventListener('toast', (e) => { const d = e.detail || {}; window.toast(d.message || d.value, d.kind); });

  // After htmx swaps, bring Alpine and Basecoat up on the new DOM
  document.body.addEventListener('htmx:afterSettle', (e) => {
    if (window.Alpine && e.detail && e.detail.elt) window.Alpine.initTree(e.detail.elt);
    if (window.basecoat && window.basecoat.initAll) window.basecoat.initAll();
  });
  document.body.addEventListener('htmx:responseError', (e) => {
    let msg = 'Something went wrong';
    try { msg = JSON.parse(e.detail.xhr.responseText).detail || msg; } catch (_) {}
    window.toast(msg, 'error');
  });

  // Action routes answer htmx with HX-Trigger {"posts-changed": {...}}; pages that can refresh a
  // region register window.onPostSaved (same hook the composer uses).
  document.body.addEventListener('posts-changed', (e) => {
    if (typeof window.onPostSaved === 'function') window.onPostSaved(e.detail || {});
    else location.reload();
  });
  // Region refresh helper used by pages: refreshRegion('#queue-column', '/queue/column?...')
  window.refreshRegion = (selector, url) => {
    const el = document.querySelector(selector);
    if (!el) return;
    return htmx.ajax('GET', url, { target: el, swap: 'outerHTML' });
  };

  // Sidebar: when the viewport shrinks below the breakpoint, don't leave it open as an overlay
  let wasDesktop = innerWidth >= 768;
  addEventListener('resize', () => {
    const desktop = innerWidth >= 768;
    const sb = document.getElementById('sidebar');
    if (wasDesktop && !desktop && sb && sb.close) sb.close();
    wasDesktop = desktop;
  });

  // Composer modal: loaded on demand into #publish-modal (Phase B wires the pages to it)
  window.openComposer = async (params = {}) => {
    const dlg = document.getElementById('publish-modal');
    if (!dlg) { location.href = '/compose?' + new URLSearchParams(params); return; }
    const body = dlg.querySelector('[data-modal-body]');
    body.innerHTML = '<p class="p-6 text-sm text-mute">Loading…</p>';
    if (!dlg.open) dlg.showModal();
    await htmx.ajax('GET', '/compose/modal?' + new URLSearchParams(params), { target: body, swap: 'innerHTML' });
  };
  document.body.addEventListener('post-saved', (e) => {
    const dlg = document.getElementById('publish-modal');
    const wasModal = dlg && dlg.open;
    if (wasModal) dlg.close();
    // Pages that can refresh a region register window.onPostSaved; otherwise reload in place.
    if (typeof window.onPostSaved === 'function') window.onPostSaved(e.detail || {});
    else if (wasModal) setTimeout(() => location.reload(), 350);
  });
})();
