/* Commands tab: a project-owned list of ready-made prompts (commands.json). Clicking one sends it to the Claude session
   watching the page (comments capability), or copies it when no session can be reached. Loads only commands.json. */
(function () {
  'use strict';
  var RM = window.RM;
  var esc = RM.esc;

  var CSS = [
    '.cm-intro{font-size:13px;color:var(--text-secondary);max-width:70ch;margin:0 0 14px}',
    '.cm-note{font-size:13px;color:var(--text-secondary);min-height:20px;margin:0 0 12px}',
    '.cm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;align-items:start}',
    '.cm-card{border:1px solid var(--border);border-radius:12px;background:var(--surface);padding:12px 14px}',
    '.cm-card h3{font-size:15px;margin-bottom:2px}',
    '.cm-blurb{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}',
    '.cm-row{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--border)}',
    '.cm-row:first-of-type{border-top:0}',
    '.cm-btn{flex:none;font:inherit;font-size:12.5px;font-weight:500;border:1px solid var(--accent);color:var(--accent);background:none;border-radius:999px;padding:4px 12px;cursor:pointer;white-space:nowrap}',
    '.cm-btn:hover{background:var(--surface-2)}',
    '.cm-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}',
    '.cm-btn[disabled]{opacity:.5;cursor:default}',
    '.cm-txt{min-width:0}',
    '.cm-lab{font-size:13.5px;font-weight:600}',
    '.cm-desc{font-size:12.5px;color:var(--text-secondary);margin-top:1px;line-height:1.4}',
    '.cm-prompt{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--text-secondary);margin-top:4px;overflow-wrap:anywhere}'
  ].join('\n');

  var chan = null;   // resolves to the comments capability or null
  function comments() {
    if (chan) return chan;
    chan = Promise.resolve().then(function () {
      if (!(window.claude && typeof window.claude.use === 'function')) return null;
      return window.claude.use('comments');
    }).then(function (c) { return c && typeof c.sendToClaude === 'function' ? c : null; }, function () { return null; });
    return chan;
  }

  function mount(root, data) {
    var d = data && data.commands;
    if (!d || !Array.isArray(d.groups)) {
      root.innerHTML = '<div class="error-box"><b>commands.json</b> has no command groups.</div>';
      return;
    }
    if (!document.getElementById('cm-style')) {
      var st = document.createElement('style'); st.id = 'cm-style'; st.textContent = CSS; document.head.appendChild(st);
    }
    var prompts = [];
    var h = (d.intro ? '<p class="cm-intro">' + esc(d.intro) + '</p>' : '') + '<p class="cm-note" id="cm-note" role="status" aria-live="polite"></p><div class="cm-grid">';
    d.groups.forEach(function (g) {
      h += '<section class="cm-card"><h3>' + esc(g.name) + '</h3>' + (g.blurb ? '<p class="cm-blurb">' + esc(g.blurb) + '</p>' : '');
      (g.commands || []).forEach(function (c) {
        var i = prompts.push(c.prompt) - 1;
        h += '<div class="cm-row"><button type="button" class="cm-btn" data-i="' + i + '">Ask Claude</button><div class="cm-txt"><div class="cm-lab">' + esc(c.label) + '</div>' +
          (c.note ? '<div class="cm-desc">' + esc(c.note) + '</div>' : '') + '<div class="cm-prompt">' + esc(c.prompt) + '</div></div></div>';
      });
      h += '</section>';
    });
    root.innerHTML = h + '</div>';
    var note = root.querySelector('#cm-note');

    function fallback(text, why) {
      RM.copy(text).then(function () { note.textContent = why + ' Prompt copied; paste it into the chat.'; });
    }
    root.addEventListener('click', function (ev) {
      var btn = ev.target.closest('.cm-btn');
      if (!btn) return;
      var text = prompts[Number(btn.getAttribute('data-i'))];
      btn.disabled = true; note.textContent = '';
      comments().then(function (c) {
        if (!c) { fallback(text, 'No Claude session is reachable from this page.'); return; }
        return Promise.resolve().then(function () { return c.canSendToClaude(); }).then(function (state) {
          if (state !== 'available') { fallback(text, 'No Claude session is watching this page right now.'); return; }
          return Promise.resolve(c.anchorFor(btn)).then(function (anchor) { return c.sendToClaude({ anchor: anchor, text: text }); })
            .then(function () { note.textContent = 'Sent to Claude: ' + text.slice(0, 80) + (text.length > 80 ? '…' : ''); });
        });
      }).catch(function (err) {
        var code = err && err.code;
        fallback(text, code === 'consent_required' ? 'Page comments were not allowed.' : code === 'rate_limited' ? 'Too many requests just now.' : 'Could not send.');
      }).then(function () { setTimeout(function () { btn.disabled = false; }, 1500); });
    });
  }

  RM.tabs = RM.tabs || {};
  RM.tabs.commands = { mount: mount };
})();
