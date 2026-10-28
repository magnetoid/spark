// Composer state: per-platform text, live limits, media, AI helpers.
function composer(init) {
  return {
    content: init.content || '',
    link: init.link || '',
    media: init.media || [],
    mediaIds: init.mediaIds || [],
    selected: init.selected || [],
    overrides: init.overrides || {},
    firstComments: init.firstComments || {},
    threads: init.threads || {},
    brand: init.brand || {},
    limits: init.limits || {},
    previewText(id) {
      const t = this.textFor(id) || '';
      return t.length > 320 ? t.slice(0, 320) + '…' : t;
    },
    // --- threads ("Split into thread", like Buffer) ---
    hasThread(id) { return (this.threads[id] || []).length > 0; },
    threadOver(id) {
      const max = this.limits[id] ? this.limits[id].max : Infinity;
      return (this.threads[id] || []).some(t => t.length > max);
    },
    splitThread(id) {
      // Paragraphs first, then sentences, then hard wraps; each part within the limit
      // minus room for a " (n/m)" counter.
      const max = Math.max(40, this.limits[id].max - 8);
      const source = (this.overrides[id] || this.content || '').trim();
      const parts = [];
      const push = (s) => { s = s.trim(); if (s) parts.push(s); };
      for (const para of source.split(/\n{2,}/)) {
        if (para.length <= max) { push(para); continue; }
        let buf = '';
        for (const sent of para.split(/(?<=[.!?])\s+/)) {
          if ((buf + ' ' + sent).trim().length <= max) { buf = (buf + ' ' + sent).trim(); continue; }
          push(buf); buf = '';
          if (sent.length <= max) { buf = sent; continue; }
          for (let i = 0; i < sent.length; i += max) push(sent.slice(i, i + max));
        }
        push(buf);
      }
      // Merge short neighbours so items aren't tiny
      const merged = [];
      for (const p of parts) {
        const last = merged[merged.length - 1];
        if (last !== undefined && (last + '\n\n' + p).length <= max) merged[merged.length - 1] = last + '\n\n' + p;
        else merged.push(p);
      }
      if (merged.length < 2) return;
      const n = merged.length;
      const numbered = merged.map((p, i) => n > 1 ? `${p} (${i + 1}/${n})` : p);
      this.overrides[id] = numbered[0];
      this.threads[id] = numbered.slice(1);
      this.editing = id;
      this.validate();
    },
    clearThread(id) { this.threads[id] = []; this.validate(); },
    setThreadItem(id, i, value) { const t = [...(this.threads[id] || [])]; t[i] = value; this.threads[id] = t; },
    removeThreadItem(id, i) { const t = [...(this.threads[id] || [])]; t.splice(i, 1); this.threads[id] = t; },
    addThreadItem(id) { this.threads[id] = [...(this.threads[id] || []), '']; },
    ai: !!init.ai,
    problems: {},
    editing: null,
    picker: false,
    busy: false,
    error: '',
    _t: null,

    textFor(id) { return this.overrides[id] || this.content; },
    over(id) { return this.limits[id] && this.textFor(id).length > this.limits[id].max; },
    get hasProblems() {
      return this.selected.some(id => this.over(id) || this.threadOver(id) || (this.problems[id] || []).length);
    },
    toggle(id) {
      const i = this.selected.indexOf(id);
      i >= 0 ? this.selected.splice(i, 1) : this.selected.push(id);
      this.validate();
    },
    addMedia(m) {
      if (!this.mediaIds.includes(m.id)) { this.media.push(m); this.mediaIds.push(m.id); }
      this.validate();
    },
    removeMedia(id) {
      this.media = this.media.filter(m => m.id !== id);
      this.mediaIds = this.mediaIds.filter(x => x !== id);
      this.validate();
    },
    syncHidden() {},
    validate() {
      clearTimeout(this._t);
      this._t = setTimeout(async () => {
        const targets = {};
        this.selected.forEach(id => targets[id] = this.textFor(id));
        if (!Object.keys(targets).length) { this.problems = {}; return; }
        try {
          const r = await fetch('/compose/preview', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({targets, media_ids: this.mediaIds, link: this.link || null})});
          if (r.ok) this.problems = await r.json();
        } catch (e) { /* offline: keep client-side checks only */ }
      }, 250);
    },
    platformsSelected() {
      return [...new Set(this.selected.map(id => this.limits[id].platform))];
    },
    async _ai(url, body) {
      this.busy = true; this.error = '';
      try {
        const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'AI request failed');
        return data;
      } catch (e) { this.error = e.message; return null; }
      finally { this.busy = false; }
    },
    async aiGenerate(brief, url) {
      const platforms = this.platformsSelected();
      const data = await this._ai('/ai/generate', {brief, url, platforms: platforms.length ? platforms : ['x', 'linkedin'], link: this.link || null});
      if (!data) return;
      const byPlatform = {};
      data.drafts.forEach(d => { if (!byPlatform[d.platform]) byPlatform[d.platform] = d; });
      const first = data.drafts[0];
      if (first) this.content = first.text;
      this.selected.forEach(id => {
        const d = byPlatform[this.limits[id].platform];
        if (d && d.text !== this.content) this.overrides[id] = d.text;
      });
      this.validate();
    },
    async aiRewrite(instruction) {
      const data = await this._ai('/ai/rewrite', {text: this.content, instruction});
      if (data) { this.content = data.text; this.validate(); }
    },
    async aiAdapt(id) {
      const data = await this._ai('/ai/rewrite', {text: this.content, platform: this.limits[id].platform,
        instruction: `Adapt this for ${this.limits[id].label}, keeping the message. Fit within ${this.limits[id].max} characters.`});
      if (data) { this.overrides[id] = data.text; this.editing = id; this.validate(); }
    },
    async aiHashtags() {
      const data = await this._ai('/ai/hashtags', {text: this.content});
      if (data) { this.content = (this.content.trimEnd() + '\n\n' + data.hashtags.map(h => '#' + h).join(' ')).trim(); this.validate(); }
    },
  };
}
// Media picker tiles call this (rendered by HTMX partials).
function pickMedia(el) {
  const root = el.closest('[x-data]');
  const data = Alpine.$data(document.querySelector('[x-data^="composer"]'));
  data.addMedia({id: +el.dataset.id, url: el.dataset.url, video: el.dataset.video === '1', name: el.dataset.name});
}
