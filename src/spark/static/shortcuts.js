// Keyboard shortcuts and the command palette.
//   c        new post            g q  queue        g c  calendar     g i  ideas
//   g o      overview            g p  all posts    g n  inbox        /    search / palette
//   ?        shortcut help       Esc  close
(() => {
  const typing = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
  const go = { o: '/', q: '/queue', c: '/calendar', i: '/ideas', p: '/posts', n: '/inbox', a: '/analytics', s: '/settings' };
  let pendingG = false, gTimer = null;

  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey) {
      if (e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
      return;
    }
    if (typing(e) || document.documentElement.dataset.shortcuts === 'off') return;
    if (pendingG) {
      pendingG = false; clearTimeout(gTimer);
      if (go[e.key]) { e.preventDefault(); location.href = go[e.key]; }
      return;
    }
    switch (e.key) {
      case 'c': e.preventDefault(); window.openComposer ? window.openComposer({}) : (location.href = '/compose'); break;
      case 'g': pendingG = true; gTimer = setTimeout(() => (pendingG = false), 1200); break;
      case '/': e.preventDefault(); openPalette(); break;
      case '?': e.preventDefault(); document.getElementById('shortcuts-help')?.showModal(); break;
    }
  });

  // --- palette -----------------------------------------------------------------
  let items = null;
  async function openPalette() {
    const dlg = document.getElementById('palette');
    if (!dlg) return;
    if (!items) {
      try { items = await (await fetch('/api/palette')).json(); } catch (_) { items = []; }
    }
    const state = Alpine.$data(dlg.querySelector('[x-data]'));
    state.items = items; state.q = ''; state.active = 0;
    dlg.showModal();
    setTimeout(() => dlg.querySelector('input')?.focus(), 30);
  }
  window.openPalette = openPalette;

  window.palette = () => ({
    q: '', items: [], active: 0,
    get results() {
      const q = this.q.trim().toLowerCase();
      const list = q ? this.items.filter(i => (i.label + ' ' + (i.hint || '')).toLowerCase().includes(q)) : this.items;
      return list.slice(0, 12);
    },
    run(i) {
      const it = this.results[i]; if (!it) return;
      document.getElementById('palette').close();
      if (it.action === 'compose') window.openComposer(it.params || {});
      else if (it.href) location.href = it.href;
    },
    key(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); this.active = Math.min(this.active + 1, this.results.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); this.active = Math.max(this.active - 1, 0); }
      else if (e.key === 'Enter') { e.preventDefault(); this.run(this.active); }
    },
  });
})();
