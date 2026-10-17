/* Roadmap shell loader: tabs.json -> header + tab bar + hash routing; each tab script loads on first use. */
(function () {
  'use strict';
  var RM = window.RM = window.RM || {};
  RM.tabs = RM.tabs || {};

  RM.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  // small mono chip showing a phase/feature/story id beside its name, so chat ids can be matched to names
  RM.idChip = function (kind, id) {
    return '<span class="id-chip mono" title="' + RM.esc(kind + ' ' + id) + '">' + RM.esc(id) + '</span>';
  };
  RM.fmtDate = function (v) {
    var d = new Date(v);
    if (isNaN(d)) return String(v == null ? '' : v);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };
  RM.fmtNum = function (n) { return Number(n || 0).toLocaleString('en-US'); };
  RM.fmtTok = function (n) {
    n = Number(n || 0);
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return String(Math.round(n));
  };
  RM.copy = function (text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    } catch (e) { /* fall through */ }
    return new Promise(function (resolve) {
      try {
        var t = document.createElement('textarea');
        t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
        document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
      } catch (e) { /* ignore */ }
      resolve();
    });
  };
  RM.store = function (key, value) {
    try {
      if (arguments.length > 1) { localStorage.setItem('rm:' + key, JSON.stringify(value)); return value; }
      var raw = localStorage.getItem('rm:' + key);
      return raw == null ? null : JSON.parse(raw);
    } catch (e) { return null; }
  };

  /* Story pieces shared by the Plan tab and the Execution flow tab (the flow opens the same details pane). They live
     here because either tab can be the first one opened, so neither tab script can own them. */
  RM.story = (function () {
    var esc = RM.esc, fmtNum = RM.fmtNum, fmtTok = RM.fmtTok;
    var statusMeta = {
      'done':        { label: 'Done',          color: 'var(--status-done)' },
      'approval':    { label: 'Approval',      color: 'var(--status-approval)' },
      'review':      { label: 'Review',        color: 'var(--status-review)' },
      'progress':    { label: 'Implementing',  color: 'var(--status-progress)' },
      'plan-review': { label: 'Plan critique', color: 'var(--status-plan-review)' },
      'planning':    { label: 'Planning',      color: 'var(--status-planning)' },
      'not-started': { label: 'Not started',   color: 'var(--status-queued)' }
    };
    function modelColor(m) { return m === 'b' ? 'var(--gold)' : m === 'c' ? 'var(--slate)' : 'var(--teal)'; }
    function fmtDate(iso) {
      var d = iso ? new Date(iso + 'T00:00:00') : null;
      return d && !isNaN(d) ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : (iso || '');
    }
    function fmtDur(sec) { return sec < 60 ? Math.round(sec) + 's' : Math.floor(sec / 60) + 'm ' + Math.round(sec % 60) + 's'; }
    function agentChip(agents, agentId) {
      if (!agentId) return '<span class="unassigned">Unassigned</span>';
      var a = (agents || {})[agentId] || { name: agentId, initials: '?', model: 'a', modelLabel: '' };
      return '<span class="agent-chip">' +
        '<span class="avatar" style="background:' + modelColor(a.model) + '">' + esc(a.initials) + '</span>' +
        '<span class="agent-name">' + esc(a.name) + '</span>' +
        '<span class="model-badge model-' + esc(a.model) + ' mono">' + esc(a.modelLabel) + '</span></span>';
    }
    function statusChip(color, label) {
      return '<span class="f-status" style="background:color-mix(in srgb, ' + color + ' 18%, transparent); color:' + color + '">' + esc(label) + '</span>';
    }
    function escChip(s) {
      return (s.type === 'bug' ? '<span class="bug-chip" title="Bug fix">BUG</span>' : '') +
        (s.escalated ? '<span class="loop-chip">⬆ ' + esc(s.escalated) + '</span>' : '') +
        (s.obe ? '<span class="loop-chip" title="Overtaken by events: closed without being built">OBE</span>' : '');
    }
    function usageSection(TOK, s) {
      TOK = TOK || {};
      var u = (TOK.stories || {})[s.id] || null;
      var when = TOK.generated ? ' Figures come from the usage ledger as of ' + esc(String(TOK.generated).replace('T', ' ').replace('Z', ' UTC')) + '.' : '';
      if (!u && s.obe) return '<div class="d-sec"><h4>Token usage</h4><p>None. This story was closed as overtaken by events without being built.</p></div>';
      if (!u) return '<div class="d-sec"><h4>Token usage</h4><p>No usage recorded for this story yet. Either work has not started, or it finished before per-story tracking began (that spend is not tied to any story in the ledger).</p></div>';
      function row(k, v) { return '<span>' + k + '</span><span class="v">' + esc(v) + '</span>'; }
      return '<div class="d-sec"><h4>Token usage</h4>' +
        '<div class="tok-big">' + fmtNum(u.fresh) + ' <small>fresh tokens</small></div>' +
        '<div class="tok-table">' +
        row('New input', fmtNum(u.input)) +
        row('Written to cache', fmtNum(u.cache_write)) +
        row('Output (written by the model)', fmtNum(u.output)) +
        row('Re-read from cache', fmtNum(u.cache_read)) +
        row('Orchestrator (fresh)', fmtNum(u.orch_fresh)) +
        row('Subagents (fresh)', fmtNum(u.sub_fresh)) +
        row('Model requests', fmtNum(u.requests)) +
        row('Active time', fmtDur(u.seconds || 0)) +
        row('Models', (u.models || []).join(', ')) +
        '</div>' +
        '<p class="tok-note">Fresh tokens are the new work the model read or wrote (new input + cache writes + output). Cache re-reads are earlier conversation reused at every step, so that number is large and does not measure new work.' + when + '</p></div>';
    }
    /* env = {agents, tokens, featureOf(id), phaseOf(id), isHidden(story)}; opts = {archive, noHide} */
    function detailPanel(env, s, opts) {
      opts = opts || {};
      var f = env.featureOf(s.feature), ph = env.phaseOf(f.phase), meta = statusMeta[s.status] || statusMeta.done, d = s.details || {};
      function sec(title, inner) { return '<div class="d-sec"><h4>' + title + '</h4>' + inner + '</div>'; }
      var assign = sec('Assignment', '<div class="d-people">' + agentChip(env.agents, s.agent) +
        (s.critic ? '<div class="mc-meta"><span class="unassigned" style="font-style:normal;">Reviewed by</span>' + agentChip(env.agents, s.critic) +
          (s.loop ? '<span class="loop-chip">↻ loop ' + esc(s.loop) + '</span>' : '') + '</div>' : '') + '</div>');
      var parts = [];
      var outcomeMode = !!opts.archive || (s.status === 'done' && !s.details);
      if (outcomeMode) {
        parts.push(sec('Outcome', '<p>' + (s.outcome ? esc(s.outcome) : 'No outcome recorded.') + '</p>'));
        parts.push(assign, usageSection(env.tokens, s));
        parts.push(sec('Activity', '<p>Full log: <span class="mono">.claude/roadmap/archive/story-logs.jsonl</span> (id ' + esc(s.id) + ')</p>'));
      } else {
        parts.push(sec('Description', '<p>' + (d.desc ? esc(d.desc) : 'No description yet.') + '</p>'), assign, usageSection(env.tokens, s));
        if (d.criteria) parts.push(sec('Acceptance criteria', '<ul>' + d.criteria.map(function (c) {
          return '<li><span class="mono">' + (c.done ? '☑' : '☐') + '</span><span>' + esc(c.t) + '</span></li>'; }).join('') + '</ul>'));
        if (d.log) parts.push(sec('Activity', '<ul class="d-log">' + d.log.map(function (l) {
          return '<li><span class="mono">' + esc(l.when) + '</span><span>' + esc(l.what) + '</span></li>'; }).join('') + '</ul>'));
        if (d.notes) parts.push(sec('Notes / blockers', '<p>' + esc(d.notes) + '</p>'));
      }
      var hideControl = (!opts.archive && !opts.noHide && s.status === 'done')
        ? (env.isHidden(s) ? '<button class="toolbar-btn" data-unhide="' + esc(s.id) + '">Unhide</button>' : '<button class="toolbar-btn" data-hide="' + esc(s.id) + '">Hide task</button>')
        : '';
      return '<div class="detail" role="region" aria-label="Story details">' +
        '<div class="d-head">' +
        '<span class="d-crumb mono">' + esc(ph.name) + ' › ' + esc(f.name) + '</span>' +
        '<span class="tools-right">' + hideControl + '<button class="toolbar-btn" data-close aria-label="Close details">✕ Close</button></span>' +
        '</div>' +
        '<div class="d-body">' +
        '<h3 class="d-title">' + RM.idChip('Story', s.id) + ' ' + esc(s.name) + '</h3>' +
        '<div class="d-chips">' + statusChip(meta.color, meta.label) + escChip(s) +
        (s.completed ? '<span class="unassigned" style="font-style:normal;">Completed ' + esc(fmtDate(s.completed)) + '</span>' : '') + '</div>' +
        '<div class="d-grid">' + parts.join('') + '</div>' +
        '</div></div>';
    }
    return { statusMeta: statusMeta, modelColor: modelColor, agentChip: agentChip, statusChip: statusChip, escChip: escChip,
             usageSection: usageSection, detailPanel: detailPanel };
  })();

  function getJSON(name) {
    return fetch(name, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(name + ' (HTTP ' + r.status + ')');
      return r.json().catch(function () { throw new Error(name + ' (not valid JSON)'); });
    }, function () { throw new Error(name + ' (could not be fetched)'); });
  }

  function errorBox(root, what) {
    root.innerHTML = '<div class="error-box"><b>' + RM.esc(what.file) + '</b> failed to load. ' +
      RM.esc(what.msg) + ' Run <span class="mono">roadmap.py refresh</span> and publish again.</div>';
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error(src + ' (script could not be loaded)')); };
      document.head.appendChild(s);
    });
  }

  function start(cfg) {
    var app = document.getElementById('app');
    var tabs = cfg.tabs || [];
    app.innerHTML =
      '<div class="page"><header class="rm-head"><h1>' + RM.esc(cfg.title || 'Roadmap') + '</h1>' +
      '<p class="subtitle">' + RM.esc(cfg.subtitle || '') + '</p><div class="updated" id="rm-updated"></div>' +
      '<div class="rm-actions"><button type="button" class="rm-btn" id="rm-reload">Reload</button>' +
      '<button type="button" class="rm-btn" id="rm-ask" hidden>Ask Claude to update</button>' +
      '<span class="rm-note" id="rm-ask-hint"></span><span class="rm-note" id="rm-status" role="status" aria-live="polite"></span></div></header>' +
      '<nav class="rm-tabs" role="tablist" aria-label="Dashboard tabs"></nav><main id="rm-panels"></main></div>';
    var nav = app.querySelector('.rm-tabs');
    var panels = app.querySelector('#rm-panels');
    var newest = '';
    var state = {};

    function noteGenerated(data) {
      Object.keys(data).forEach(function (k) {
        var g = data[k] && data[k].generated;
        if (g && String(g) > newest) newest = String(g);
      });
      if (newest) document.getElementById('rm-updated').textContent = 'Updated ' + newest.replace('T', ' ');
    }

    tabs.forEach(function (tab) {
      var a = document.createElement('a');
      a.href = '#' + tab.id; a.id = 'rm-tab-' + tab.id; a.setAttribute('role', 'tab');
      a.textContent = tab.title;
      nav.appendChild(a);
      var p = document.createElement('section');
      p.className = 'tab-panel'; p.id = 'rm-panel-' + tab.id; p.hidden = true;
      p.setAttribute('role', 'tabpanel');
      panels.appendChild(p);
    });

    function activate(tab) {
      if (state[tab.id]) return Promise.resolve();
      state[tab.id] = true;
      var root = document.getElementById('rm-panel-' + tab.id);
      var failing = tab.script;
      root.textContent = 'Loading...';
      return (RM.tabs[tab.id] ? Promise.resolve() : loadScript(tab.script)).then(function () {
        var names = Object.keys(tab.data || {});
        return Promise.all(names.map(function (k) {
          failing = tab.data[k];
          return getJSON(tab.data[k]);
        })).then(function (vals) {
          var data = {};
          names.forEach(function (k, i) { data[k] = vals[i]; });
          return data;
        });
      }).then(function (data) {
        noteGenerated(data);
        var mod = RM.tabs[tab.id];
        if (!mod || typeof mod.mount !== 'function') throw new Error(tab.script + ' did not register RM.tabs.' + tab.id);
        var ctx = {
          tab: tab,
          load: function (name) {
            // a declared `lazy` key resolves to its file; anything else is tried as a literal flat
            // file name in .claude/roadmap (a tab's `lazyGlob` set grows without editing tabs.json)
            var file = (tab.lazy || {})[name] || name;
            return getJSON(file);
          }
        };
        root.textContent = '';
        mod.mount(root, data, ctx);
      }).catch(function (e) {
        var msg = String(e && e.message || e);
        var m = msg.match(/^(\S+) \((.*)\)$/);
        errorBox(root, m ? { file: m[1], msg: m[2] + '.' } : { file: failing, msg: msg + '.' });
      });
    }

    function route() {
      var id = (location.hash || '').replace(/^#/, '');
      var tab = tabs.filter(function (t) { return t.id === id; })[0] || tabs[0];
      if (!tab) return Promise.resolve();
      tabs.forEach(function (t) {
        var on = t.id === tab.id;
        document.getElementById('rm-panel-' + t.id).hidden = !on;
        document.getElementById('rm-tab-' + t.id).setAttribute('aria-selected', on ? 'true' : 'false');
      });
      return activate(tab);
    }

    function reload() {
      var btn = document.getElementById('rm-reload');
      var st = document.getElementById('rm-status');
      btn.disabled = true; st.textContent = 'Reloading...';
      var before = newest;
      var names = [];
      tabs.forEach(function (t) {
        if (state[t.id]) Object.keys(t.data || {}).forEach(function (k) { names.push(t.data[k]); });
      });
      Promise.all([getJSON('tabs.json')].concat(names.map(getJSON))).then(function (vals) {
        var data = {};
        vals.slice(1).forEach(function (v, i) { data[i] = v; });
        newest = '';
        noteGenerated(data);
        state = {};
        return route();
      }).then(function () {
        st.textContent = (newest && newest === before) ? 'Already up to date' :
          'Reloaded, data generated ' + (newest ? newest.replace('T', ' ') : 'unknown');
      }).catch(function (e) {
        st.textContent = 'Reload failed: ' + String(e && e.message || e);
      }).then(function () { btn.disabled = false; });
    }

    document.getElementById('rm-reload').addEventListener('click', reload);
    window.addEventListener('hashchange', route);
    route();
    RM.initHeaderActions();
  }

  /* "Ask Claude to update": shown only when the comments capability exists and can reach a Claude session. */
  var ASK_TEXT = 'Please refresh the dashboard: run roadmap.py refresh, then publish only the changed files.';
  var ask = { c: null, state: '', dead: false, until: 0, last: 0, timer: null };

  function askEls() {
    return { btn: document.getElementById('rm-ask'), hint: document.getElementById('rm-ask-hint'),
             st: document.getElementById('rm-status') };
  }
  function applyAsk(s) {
    var e = askEls();
    if (!e.btn || ask.dead) return;
    ask.state = s;
    e.hint.textContent = s === 'no_session' ? 'No Claude session is watching this page right now. Ask in the chat instead.' :
      s === 'writers_only' ? 'Only editors can ask Claude from here.' : '';
    if (s === 'available' || s === 'no_session' || s === 'writers_only') {
      e.btn.hidden = false;
      e.btn.disabled = s !== 'available' || Date.now() < ask.until;
    } else {
      e.btn.hidden = true; e.btn.disabled = true;
    }
  }
  function recheckAsk() {
    if (!ask.c || ask.dead) return Promise.resolve();
    ask.last = Date.now();
    return Promise.resolve().then(function () { return ask.c.canSendToClaude(); })
      .then(applyAsk, function () { applyAsk('off'); });
  }
  /* Send `text` to the watching Claude session, anchored on `btn`; `st` shows the outcome. Used by the header
     button and by tab buttons (the Tasks tab asks for a tasks-only update). Disables `btn` for 60 s after a send. */
  function sendAsk(btn, text, st, sentMsg) {
    var e = askEls(), c = ask.c;
    if (!c || btn.disabled) return;
    btn.disabled = true; st.textContent = '';
    Promise.resolve().then(function () { return c.anchorFor(btn); })
      .then(function (anchor) { return c.sendToClaude({ anchor: anchor, text: text }); })
      .then(function () {
        st.textContent = sentMsg;
        ask.until = Date.now() + 60000;
        clearTimeout(ask.timer);
        ask.timer = setTimeout(function () { if (ask.state === 'available' && !ask.dead) btn.disabled = false; }, 60000);
      }, function (err) {
        var code = err && err.code;
        if (code === 'forbidden') {
          ask.dead = true; btn.hidden = true; btn.disabled = true;
          e.hint.textContent = 'Commenting from the page is off here.';
        } else if (code === 'consent_required') {
          st.textContent = 'Not sent: allow page comments when asked.'; btn.disabled = false;
        } else if (code === 'rate_limited') {
          st.textContent = 'Slow down; try again shortly.'; btn.disabled = false;
        } else if (code === 'claude_unavailable') {
          recheckAsk(); btn.disabled = false;
        } else {
          st.textContent = 'Could not send; ask in the chat.'; btn.disabled = false;
        }
      });
  }
  function onAsk() {
    var e = askEls();
    sendAsk(e.btn, ASK_TEXT, e.st, 'Update requested. Claude will refresh this page; press Reload in a minute.');
  }
  /* For tab buttons: true when a Claude session can be asked from this page right now. */
  RM.canAskClaude = function () { return !!ask.c && !ask.dead && ask.state === 'available'; };
  RM.askClaude = function (btn, text, st, sentMsg) { sendAsk(btn, text, st, sentMsg); };
  RM.initHeaderActions = function () {
    var e = askEls();
    if (!e.btn) return Promise.resolve();
    e.btn.hidden = true; e.hint.textContent = '';
    ask.c = null; ask.dead = false; ask.until = 0; ask.state = ''; clearTimeout(ask.timer);
    if (!(window.claude && typeof window.claude.use === 'function')) return Promise.resolve();
    return Promise.resolve().then(function () { return window.claude.use('comments'); }).then(function (c) {
      if (!c || typeof c.canSendToClaude !== 'function') return;
      ask.c = c;
      if (!e.btn._bound) { e.btn._bound = true; e.btn.addEventListener('click', onAsk); }
      return recheckAsk();
    }).catch(function () { /* stay hidden */ });
  };
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && ask.c && !ask.dead && Date.now() - ask.last > 30000) recheckAsk();
  });

  getJSON('tabs.json').then(start).catch(function (e) {
    var app = document.getElementById('app');
    app.innerHTML = '<div class="page"></div>';
    errorBox(app.firstChild, { file: 'tabs.json', msg: String(e && e.message || e) + '.' });
  });
})();
