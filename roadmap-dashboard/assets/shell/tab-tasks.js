/* Tasks tab: the orchestrator's own current task list (tasks.json), not the Phase/Feature/Story plan.
   Updated only when the user asks (`roadmap.py tasks-set` / `tasks-archive`), never by refresh. The
   archive list (tasks-index.json) is eager and small; each archived list's full items load only when
   its row is opened. The "Refresh tasks" button refetches only tasks.json and tasks-index.json and
   re-renders in place (ctx.load falls back to the file name itself for names tabs.json does not declare
   under `lazy`, matching the tab's `lazyGlob`).
   "My to-do" (top of the tab) is the user's own list, live in the artifact database (`db` capability,
   collection `ownerTodos`, one document per item: kind task|question, title, detail, source, created, order,
   status open|answered|done|closed, answer, answeredAt, doneAt). `claude.use("db")` is resolved once and the
   collection is subscribed once per tab mount (the old subscription is dropped on remount). Tasks have a
   Done tick; questions have an answer box and a Save answer button; the user can add a task. With no db
   (a local `serve`, or not granted) the section shows one note and the rest of the tab is unaffected.
   Claude adds items and reads answers with ArtifactData on the same collection. */
(function () {
  'use strict';
  var RM = window.RM;
  var esc = RM.esc;
  var statusMeta = RM.story.statusMeta;
  var DOT = { pending: statusMeta['not-started'].color, active: statusMeta.progress.color, done: statusMeta.done.color };
  var LABEL = { pending: 'Pending', active: 'Active', done: 'Done' };

  var CSS = [
    '.tk-summary{font-size:13px;color:var(--text-secondary);margin:0 0 14px}',
    '.tk-title{font-size:16px;font-weight:600;margin:0 0 4px}',
    '.tk-empty{font-size:13.5px;color:var(--text-secondary);padding:10px 0}',
    '.tk-list{display:flex;flex-direction:column;gap:6px;margin:0 0 26px}',
    '.tk-row{display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;background:var(--surface)}',
    '.tk-row.is-done .tk-text{color:var(--text-secondary);text-decoration:line-through}',
    '.tk-dot{width:9px;height:9px;border-radius:50%;flex:none}',
    '.tk-text{flex:1;min-width:0;font-size:13.5px}',
    '.tk-status{font-size:11px;color:var(--text-secondary);flex:none}',
    '.tk-section-head{display:flex;align-items:center;justify-content:space-between;margin:0 0 8px}',
    '.tk-section-head h2{font-size:14px;margin:0}',
    '.tk-arch-row{border:1px solid var(--border);border-radius:10px;background:var(--surface);margin-bottom:8px;overflow:hidden}',
    '.tk-arch-head{width:100%;text-align:left;display:flex;align-items:center;gap:10px;padding:10px 12px;background:none;border:0;font:inherit;cursor:pointer;color:var(--text)}',
    '.tk-arch-head:hover{background:var(--surface-2)}',
    '.tk-chev{transition:transform .15s;color:var(--text-secondary);flex:none}',
    '.tk-arch-row.open .tk-chev{transform:rotate(90deg)}',
    '.tk-arch-title{flex:1;min-width:0;font-size:13.5px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.tk-arch-meta{flex:none;font-size:11.5px;color:var(--text-secondary)}',
    '.tk-arch-body{padding:0 12px 12px 34px}',
    '.tk-arch-note{font-size:12.5px;color:var(--text-secondary)}',
    '.tk-todo{margin:0 0 26px}',
    '.tk-todo-note{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}',
    '.tk-todo-list{display:flex;flex-direction:column;gap:6px;margin:0 0 10px}',
    '.tk-todo-row{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;background:var(--surface)}',
    '.tk-todo-row.is-done .tk-todo-title{color:var(--text-secondary);text-decoration:line-through}',
    '.tk-todo-main{flex:1;min-width:0}',
    '.tk-todo-title{font-size:13.5px;font-weight:500}',
    '.tk-todo-sub{font-size:12px;color:var(--text-secondary);margin-top:2px;white-space:pre-wrap}',
    '.tk-todo-ans{width:100%;box-sizing:border-box;min-height:60px;margin-top:6px;padding:6px 8px;font:inherit;font-size:13px;color:var(--text);background:var(--surface-2);border:1px solid var(--border);border-radius:8px;resize:vertical}',
    '.tk-todo-actions{display:flex;align-items:center;gap:8px;margin-top:6px}',
    '.tk-todo-add{display:flex;gap:8px;margin:0 0 8px}',
    '.tk-todo-add input{flex:1;min-width:0;padding:6px 8px;font:inherit;font-size:13px;color:var(--text);background:var(--surface-2);border:1px solid var(--border);border-radius:8px}',
    '.tk-todo-more{margin:0 0 8px}',
    '.tk-todo-more summary{cursor:pointer;font-size:13px;color:var(--text-secondary)}',
    '.tk-todo-more .tk-todo-list{margin-top:8px}'
  ].join('\n');

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(String(iso).replace('Z', '') + 'Z');
    return isNaN(d) ? String(iso) : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function taskRow(it) {
    return '<div class="tk-row' + (it.status === 'done' ? ' is-done' : '') + '">' +
      '<span class="tk-dot" style="background:' + (DOT[it.status] || DOT.pending) + '"></span>' +
      '<span class="tk-text">' + RM.idChip('Task', it.id) + ' ' + esc(it.text) + '</span>' +
      '<span class="tk-status">' + esc(LABEL[it.status] || it.status) + '</span></div>';
  }

  var NO_DB = 'My to-do needs the live dashboard on claude.ai (the database is not available in this view).';
  var COLL = 'ownerTodos';
  var ASK_TODO = 'The user updated My to-do in the dashboard (answers or done items). Read collection ownerTodos with ArtifactData, act on answered and done items, then mark them closed.';
  var dbP = null;

  // resolves the db namespace or null; memoized, never throws
  function getDb() {
    if (!dbP) {
      dbP = Promise.resolve().then(function () {
        return (window.claude && typeof window.claude.use === 'function') ? window.claude.use('db') : null;
      }).then(function (db) { return db || null; }, function () { return null; });
    }
    return dbP;
  }

  function mount(root, data, ctx) {
    if (!document.getElementById('tk-style')) {
      var st = document.createElement('style'); st.id = 'tk-style'; st.textContent = CSS; document.head.appendChild(st);
    }
    if (root.__tkClick) root.removeEventListener('click', root.__tkClick);
    if (root.__tkChange) root.removeEventListener('change', root.__tkChange);
    if (root.__tkInput) root.removeEventListener('input', root.__tkInput);
    if (root.__tkUnsub) { try { root.__tkUnsub(); } catch (e) { /* already gone */ } root.__tkUnsub = null; }
    var gen = (root.__tkGen = (root.__tkGen || 0) + 1);
    root.innerHTML = '<div class="tk-section-head"><span class="tk-arch-meta" id="tk-refresh-status" role="status" aria-live="polite"></span>' +
      '<button type="button" class="rm-btn" id="tk-ask">Ask Claude to update tasks</button> <button type="button" class="rm-btn" id="tk-refresh">Reload tasks</button></div><div id="tk-todo" class="tk-todo"></div><div id="tk-body"></div>';
    var body = root.querySelector('#tk-body');
    var todoEl = root.querySelector('#tk-todo');
    var index = [];
    var loaded = {};

    function render(d) {
      var tasks = (d && d.tasks) || { items: [] };
      tasks.items = tasks.items || [];
      index = ((d && d.index) || {}).archives || [];
      loaded = {};
      var done = tasks.items.filter(function (it) { return it.status === 'done'; }).length;

      var h = '';
      if (tasks.title) h += '<h2 class="tk-title">' + esc(tasks.title) + '</h2>';
      h += '<p class="tk-summary">' + (tasks.items.length
        ? done + ' of ' + tasks.items.length + ' done' + (tasks.updated ? ' · updated ' + esc(fmtTime(tasks.updated)) : '')
        : 'No current task list.') + '</p>';
      h += '<div class="tk-list">' + (tasks.items.length ? tasks.items.map(taskRow).join('')
        : '<div class="tk-empty">Nothing in progress right now.</div>') + '</div>';

      h += '<div class="tk-section-head"><h2>Archive</h2><span class="tk-arch-meta">' + index.length + (index.length === 1 ? ' list' : ' lists') + '</span></div>';
      h += index.length ? index.map(function (e, i) {
        return '<div class="tk-arch-row" data-i="' + i + '">' +
          '<button type="button" class="tk-arch-head" data-toggle="' + i + '" aria-expanded="false">' +
          '<span class="tk-chev">▶</span>' +
          '<span class="tk-arch-title">' + esc(e.title || 'Untitled list') + '</span>' +
          '<span class="tk-arch-meta">' + esc(e.done || 0) + '/' + esc(e.count || 0) + ' done · ' + esc(fmtTime(e.archived)) + '</span>' +
          '</button><div class="tk-arch-body" hidden></div></div>';
      }).join('') : '<p class="tk-empty">No archived lists yet.</p>';
      body.innerHTML = h;
    }
    render(data);

    // ---- My to-do (artifact database) ----
    var T = { db: null, ready: false, docs: [], readOnly: false, dead: false, msg: '', savedAt: {}, pending: {}, drafts: {}, newTitle: '' };

    function cssId(v) { return (window.CSS && window.CSS.escape) ? window.CSS.escape(v) : String(v).replace(/"/g, '\\"'); }
    function sortOpen(a, b) {
      var ao = typeof a.d.order === 'number' ? a.d.order : Infinity;
      var bo = typeof b.d.order === 'number' ? b.d.order : Infinity;
      if (ao !== bo) return ao < bo ? -1 : 1;
      return String(a.d.created || '').localeCompare(String(b.d.created || ''));
    }
    function sortClosed(a, b) {
      var at = String(a.d.doneAt || a.d.answeredAt || a.d.created || '');
      var bt = String(b.d.doneAt || b.d.answeredAt || b.d.created || '');
      return bt.localeCompare(at);
    }
    function todoRow(it) {
      var d = it.d, id = esc(it.id), busy = T.pending[it.id], lock = (T.readOnly || T.dead || busy) ? ' disabled' : '';
      var sub = '';
      if (d.detail) sub += '<div class="tk-todo-sub">' + esc(d.detail) + '</div>';
      if (d.source) sub += '<div class="tk-todo-sub">' + esc(d.source) + '</div>';
      if (d.kind === 'question') {
        var val = T.drafts[it.id] !== undefined ? T.drafts[it.id] : (d.answer || '');
        return '<div class="tk-todo-row" data-id="' + id + '"><div class="tk-todo-main">' +
          '<div class="tk-todo-title">' + esc(d.title || '') + '</div>' + sub +
          '<textarea class="tk-todo-ans" data-ans="' + id + '" aria-label="Answer"' + ((T.readOnly || T.dead) ? ' disabled' : '') + '>' + esc(val) + '</textarea>' +
          '<div class="tk-todo-actions"><button type="button" class="rm-btn" data-save="' + id + '"' + lock + '>Save answer</button>' +
          '<span class="tk-arch-meta">' + (T.savedAt[it.id] ? 'Saved ' + esc(T.savedAt[it.id]) : (d.status === 'answered' && d.answeredAt ? 'Answered ' + esc(fmtTime(d.answeredAt)) : '')) + '</span></div>' +
          '</div></div>';
      }
      var isDone = d.status === 'done' || d.status === 'closed';
      return '<div class="tk-todo-row' + (isDone ? ' is-done' : '') + '" data-id="' + id + '">' +
        '<input type="checkbox" data-tick="' + id + '" aria-label="Done"' + (isDone ? ' checked' : '') + lock + (d.status === 'closed' ? ' disabled' : '') + '>' +
        '<div class="tk-todo-main"><div class="tk-todo-title">' + esc(d.title || '') + '</div>' + sub + '</div></div>';
    }
    function renderTodo() {
      if (root.__tkGen !== gen) return;
      var active = document.activeElement, focusId = null, focusKey = null, ss = 0, se = 0;
      if (active && todoEl.contains(active)) {
        focusKey = active.hasAttribute('data-ans') ? 'ans' : (active.id === 'tk-todo-new' ? 'new' : null);
        if (focusKey === 'ans') focusId = active.getAttribute('data-ans');
        try { ss = active.selectionStart; se = active.selectionEnd; } catch (e) { /* not a text control */ }
      }
      var h = '<div class="tk-section-head"><h2>My to-do</h2><span class="tk-arch-meta" id="tk-todo-status" role="status" aria-live="polite"></span></div>';
      if (!T.ready) {
        h += '<p class="tk-todo-note">Loading…</p>';
      } else if (!T.db) {
        h += '<p class="tk-todo-note">' + esc(NO_DB) + '</p>';
      } else if (T.dead) {
        h += '<p class="tk-todo-note">To-do unavailable.</p>';
      } else {
        var open = T.docs.filter(function (it) { return it.d.status === 'open' || !it.d.status; }).sort(sortOpen);
        var rest = T.docs.filter(function (it) { return it.d.status && it.d.status !== 'open'; }).sort(sortClosed);
        if (T.readOnly) h += '<p class="tk-todo-note">The database refused a write, so this section is read-only for this visit.</p>';
        if (T.msg) h += '<p class="tk-todo-note">' + esc(T.msg) + '</p>';
        if (!T.readOnly) h += '<div class="tk-todo-add"><input type="text" id="tk-todo-new" placeholder="Add a to-do for yourself" aria-label="New to-do" value="' + esc(T.newTitle) + '">' +
          '<button type="button" class="rm-btn" id="tk-todo-add">Add</button></div>';
        h += '<div class="tk-todo-list">' + (open.length ? open.map(todoRow).join('') : '<div class="tk-empty">Nothing waiting on you.</div>') + '</div>';
        if (rest.length) h += '<details class="tk-todo-more"><summary>Answered and done (' + rest.length + ')</summary><div class="tk-todo-list">' + rest.map(todoRow).join('') + '</div></details>';
        if (RM.canAskClaude && RM.canAskClaude()) h += '<button type="button" class="rm-btn" id="tk-todo-ask">Tell Claude I answered</button>';
      }
      var wasOpen = !!todoEl.querySelector('.tk-todo-more[open]');
      todoEl.innerHTML = h;
      if (wasOpen) { var det = todoEl.querySelector('.tk-todo-more'); if (det) det.open = true; }
      var f = focusKey === 'ans' ? todoEl.querySelector('[data-ans="' + cssId(focusId) + '"]') : (focusKey === 'new' ? todoEl.querySelector('#tk-todo-new') : null);
      if (f) { f.focus(); try { f.setSelectionRange(ss, se); } catch (e) { /* ignore */ } }
    }

    function fail(e) {
      var c = e && e.code;
      if (c === 'invalid_argument' || c === 'transform_error') T.readOnly = true;
      else if (c === 'revoked') T.dead = true;
      else if (c === 'quota_exceeded' || c === 'resource_exhausted') T.msg = String(e.message || 'The database is full or busy. Try again later.');
      else T.msg = 'Could not save: ' + String((e && e.message) || e);
    }
    function retryOnce(fn) {
      return fn().catch(function (e) {
        if (e && e.code === 'unavailable') return new Promise(function (r) { setTimeout(r, 300 + Math.random() * 600); }).then(fn);
        throw e;
      });
    }
    // one write at a time per document id; a transient `unavailable` is retried once after a short random delay
    function write(id, fn) {
      if (T.pending[id]) return Promise.resolve(false);
      T.pending[id] = true; T.msg = ''; renderTodo();
      return retryOnce(fn).then(function () { return true; }, function (e) { fail(e); return false; })
        .then(function (ok) { delete T.pending[id]; renderTodo(); return ok; });
    }

    getDb().then(function (db) {
      if (root.__tkGen !== gen) return;
      T.db = db; T.ready = true;
      if (db) {
        try {
          root.__tkUnsub = db.collection(COLL).onSnapshot(function (snap) {
            T.docs = snap.docs.map(function (s) { return { id: s.id, d: s.data() || {} }; });
            renderTodo();
          }, function () { T.dead = true; renderTodo(); });
        } catch (e) { T.dead = true; }
      }
      renderTodo();
    });
    renderTodo();

    // refetches ONLY this tab's own data files (tasks.json, tasks-index.json); no other tab, not the header Reload
    function refresh() {
      var btn = root.querySelector('#tk-refresh');
      var status = root.querySelector('#tk-refresh-status');
      var files = (ctx.tab && ctx.tab.data) || { tasks: 'tasks.json', index: 'tasks-index.json' };
      var keys = Object.keys(files);
      btn.disabled = true; status.textContent = 'Refreshing…';
      Promise.all(keys.map(function (k) { return ctx.load(files[k]); })).then(function (vals) {
        var d = {};
        keys.forEach(function (k, i) { d[k] = vals[i]; });
        render(d);
        status.textContent = 'Tasks refreshed ' + new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' });
      }).catch(function (e) {
        status.textContent = 'Refresh failed: ' + String(e && e.message || e);
      }).then(function () { btn.disabled = false; });
    }

    // like the header "Ask Claude to update", but the request covers only the task list, not the whole dashboard
    var TASKS_ASK = 'Please update the Tasks tab only: run roadmap.py tasks-set with the current task list (tasks-archive first if the old list is finished), then publish only tasks.json and tasks-index.json. Do not refresh or publish the rest of the dashboard.';
    var askBtn = root.querySelector('#tk-ask');

    root.__tkChange = function (ev) {
      var tick = ev.target.closest && ev.target.closest('[data-tick]');
      if (!tick || !T.db) return;
      var id = tick.getAttribute('data-tick'), on = tick.checked;
      write(id, function () {
        return T.db.collection(COLL).doc(id).update(on ? { status: 'done', doneAt: new Date().toISOString() } : { status: 'open' });
      });
    };
    root.__tkInput = function (ev) {
      var a = ev.target.closest && ev.target.closest('[data-ans]');
      if (a) { T.drafts[a.getAttribute('data-ans')] = a.value; return; }
      if (ev.target.id === 'tk-todo-new') T.newTitle = ev.target.value;
    };
    root.addEventListener('change', root.__tkChange);
    root.addEventListener('input', root.__tkInput);

    root.__tkClick = function (ev) {
      var sv = ev.target.closest('[data-save]');
      if (sv && T.db) {
        var sid = sv.getAttribute('data-save');
        var ta = todoEl.querySelector('[data-ans="' + cssId(sid) + '"]');
        var text = ta ? ta.value : '';
        write(sid, function () {
          return T.db.collection(COLL).doc(sid).update({ answer: text, status: 'answered', answeredAt: new Date().toISOString() });
        }).then(function (ok) {
          if (ok) { delete T.drafts[sid]; T.savedAt[sid] = new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }); renderTodo(); }
        });
        return;
      }
      if (ev.target.closest('#tk-todo-add') && T.db) {
        var title = T.newTitle.trim();
        if (!title || T.pending.__add) return;
        T.pending.__add = true; T.msg = '';
        retryOnce(function () { return T.db.collection(COLL).add({ kind: 'task', title: title, status: 'open', created: new Date().toISOString(), source: 'owner' }); })
          .then(function () { T.newTitle = ''; }, fail)
          .then(function () { delete T.pending.__add; renderTodo(); });
        return;
      }
      if (ev.target.closest('#tk-todo-ask')) {
        if (!(RM.canAskClaude && RM.canAskClaude())) return;
        RM.askClaude(ev.target.closest('#tk-todo-ask'), ASK_TODO, todoEl.querySelector('#tk-todo-status'), 'Claude has been told. It will read your answers shortly.');
        return;
      }
      if (ev.target.closest('#tk-ask')) {
        if (!(RM.canAskClaude && RM.canAskClaude())) { root.querySelector('#tk-refresh-status').textContent = 'No Claude session is watching this page right now. Ask in the chat instead.'; return; }
        RM.askClaude(askBtn, TASKS_ASK, root.querySelector('#tk-refresh-status'), 'Task update requested. Press Reload tasks in a minute.');
        return;
      }
      if (ev.target.closest('#tk-refresh')) { refresh(); return; }
      var btn = ev.target.closest('[data-toggle]');
      if (!btn) return;
      var i = Number(btn.getAttribute('data-toggle'));
      var row = root.querySelector('.tk-arch-row[data-i="' + i + '"]');
      var abody = row.querySelector('.tk-arch-body');
      var open = !row.classList.contains('open');
      row.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
      abody.hidden = !open;
      if (!open || loaded[i]) return;
      loaded[i] = true;
      abody.innerHTML = '<p class="tk-arch-note">Loading…</p>';
      var entry = index[i];
      ctx.load(entry.file).then(function (d) {
        var items = (d && d.items) || [];
        abody.innerHTML = items.length ? '<div class="tk-list">' + items.map(taskRow).join('') + '</div>'
          : '<p class="tk-arch-note">Empty list.</p>';
      }).catch(function (e) {
        abody.innerHTML = '<p class="tk-arch-note">Could not load ' + esc(entry.file) + ': ' + esc(String(e && e.message || e)) + '</p>';
      });
    };
    root.addEventListener('click', root.__tkClick);
  }

  RM.tabs = RM.tabs || {};
  RM.tabs.tasks = { mount: mount };
})();
