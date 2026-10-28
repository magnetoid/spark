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
    brand: init.brand || {},
    limits: init.limits || {},
    previewText(id) {
      const t = this.textFor(id) || '';
      return t.length > 320 ? t.slice(0, 320) + '…' : t;
    },
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
      return this.selected.some(id => this.over(id) || (this.problems[id] || []).length);
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
