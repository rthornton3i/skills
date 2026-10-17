/* Git activity tab: chips, per-day bars, History (branch graph), collapsed branch events. */
(function () {
  'use strict';
  var RM = window.RM;
  var esc = RM.esc;

  var ROW = 30, LANE = 16, PAD = 14, R = 4.5, HALF = ROW / 2;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function dayLabel(key) {
    var p = key.split('-');
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    if (isNaN(d)) return key;
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function keyOf(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function stamp(ts) {
    var s = String(ts);
    var m = +s.slice(5, 7);
    if (!MONTHS[m - 1]) return s.slice(0, 16);
    return MONTHS[m - 1] + ' ' + (+s.slice(8, 10)) + ' ' + s.slice(11, 16);
  }
  function num(n) { return Math.round(n * 10) / 10; }

  function mount(root, data) {
    var d = data.git || {};
    var commits = d.commits || [];
    var branches = d.branches || [];
    var events = d.events || [];
    var totals = d.totals || {};
    var days = d.days || 14;

    // per-day counts over the window, oldest to newest, ending at the newest known day
    var perDay = {};
    commits.forEach(function (c) { var k = String(c.ts).slice(0, 10); perDay[k] = (perDay[k] || 0) + 1; });
    var endBase = new Date(String(d.generated || '').slice(0, 10) + 'T12:00:00');
    if (isNaN(endBase)) endBase = new Date();
    var series = [];
    for (var i = days - 1; i >= 0; i--) {
      var dt = new Date(endBase.getFullYear(), endBase.getMonth(), endBase.getDate() - i);
      var k = keyOf(dt);
      series.push({ key: k, n: perDay[k] || 0 });
    }
    var maxN = series.reduce(function (m, s) { return Math.max(m, s.n); }, 0) || 1;

    function chip(label, val) {
      return '<div class="git-chip"><b class="mono">' + esc(RM.fmtNum(val)) + '</b><span>' + esc(label) + '</span></div>';
    }

    function bars() {
      return '<div class="day-bars" role="img" aria-label="Commits per day">' + series.map(function (s) {
        var h = s.n ? Math.max(6, Math.round(s.n / maxN * 100)) : 2;
        return '<div class="day-bar' + (s.n ? '' : ' zero') + '" title="' + esc(dayLabel(s.key) + ': ' + s.n + ' commits') +
          '"><i style="height:' + h + '%"></i></div>';
      }).join('') + '</div>' +
        '<div class="day-bar-axis mono"><span>' + esc(dayLabel(series[0].key)) + '</span><span>' +
        esc(dayLabel(series[series.length - 1].key)) + '</span></div>';
    }

    function eventList() {
      if (!events.length) return '<div class="empty-note">No merges, checkouts or pulls recorded in this window.</div>';
      return '<ul class="git-list">' + events.slice(0, 40).map(function (e) {
        return '<li class="git-row"><span class="git-time mono">' + esc(String(e.ts).slice(5, 16).replace('T', ' ')) + '</span>' +
          '<span class="git-main"><span class="git-subject">' + esc(e.text) + '</span></span>' +
          '<span class="git-side"><span class="git-merge mono">' + esc(e.kind) + '</span></span></li>';
      }).join('') + '</ul>' + (events.length > 40 ? '<div class="empty-note">Showing the newest 40 of ' + esc(events.length) + '.</div>' : '');
    }

    // ---- History graph
    function refChip(r) {
      var cls = 'git-ref gg-ref mono' + (r === d.head ? ' gg-head' : '') + (r.indexOf('tag:') === 0 ? ' gg-tag' : '');
      return '<span class="' + cls + '" title="' + esc(r) + '">' + esc(r) + '</span>';
    }

    function history() {
      if (!commits.length) return '<div class="empty-note">No commits in the last ' + esc(days) + ' days.</div>';
      if (!commits.every(function (c) { return Array.isArray(c.edges) && typeof c.lane === 'number'; })) {
        return '<div class="error-box"><b>git.json</b> has no branch-graph data (schema ' + esc(d.schema || 1) +
          '). Run <span class="mono">roadmap.py git</span> and reload.</div>';
      }
      var n = commits.length;
      var lanes = Math.max(1, d.lanes || 1);
      commits.forEach(function (c) {
        c.lane = c.lane | 0;
        lanes = Math.max(lanes, c.lane + 1);
        c.edges.forEach(function (e) { lanes = Math.max(lanes, (e[1] | 0) + 1); });
      });
      var W = lanes * LANE + 12, H = n * ROW;
      var index = {};
      commits.forEach(function (c, r) { index[c.id] = r; });
      function cx(l) { return PAD + l * LANE; }
      function cy(r) { return r * ROW + HALF; }

      // Colour follows the BRANCH, not the lane: stacked branches share one straight lane in the commit graph (as in
      // git log --graph), so a change of colour is what shows where one starts. Colours are handed out in order of
      // first appearance, so neighbours differ; a commit with no known branch falls back to its lane colour.
      var branchColor = {}, nextColor = 0;
      commits.forEach(function (c) {
        if (c.branch && branchColor[c.branch] == null) { branchColor[c.branch] = nextColor % 6; nextColor++; }
      });
      function colorOf(c) { return c && c.branch && branchColor[c.branch] != null ? branchColor[c.branch] : (c ? c.lane : 0) % 6; }
      // branch point: a commit whose first-parent child is on another branch (that branch starts on top of it)
      var forks = {};
      commits.forEach(function (c) {
        var pr = c.parents && c.parents.length ? index[c.parents[0]] : null;
        if (pr == null || !c.branch || !commits[pr].branch || commits[pr].branch === c.branch) return;
        var list = forks[pr] = forks[pr] || [];
        if (list.indexOf(c.branch) < 0) list.push(c.branch);
      });

      var paths = '', stubs = {}, stubSvg = '';
      commits.forEach(function (c, r) {
        var x1 = cx(c.lane), y1 = cy(r);
        c.edges.forEach(function (e, en) {
          var pid = e[0], el = e[1] | 0, xe = cx(el);
          var col = 'gg-c' + (en === 0 || index[pid] == null ? colorOf(c) : colorOf(commits[index[pid]]));
          var p = 'M' + num(x1) + ' ' + num(y1);
          var pr = index[pid];
          if (el !== c.lane) {
            p += ' C' + num(x1) + ' ' + num(y1 + HALF * 0.6) + ' ' + num(xe) + ' ' + num(y1 + HALF * 0.4) + ' ' + num(xe) + ' ' + num(y1 + HALF);
          }
          if (pr == null) {
            var yb = H - 7;
            p += ' L' + num(xe) + ' ' + num(yb);
            if (!stubs[el]) {
              stubs[el] = 1;
              stubSvg += '<circle class="gg-stub ' + col + '" cx="' + num(xe) + '" cy="' + num(H - 4) + '" r="3">' +
                '<title>older history not loaded</title></circle>';
            }
          } else {
            var xp = cx(commits[pr].lane), yp = cy(pr);
            if (xp === xe) {
              p += ' L' + num(xp) + ' ' + num(yp);
            } else {
              p += ' L' + num(xe) + ' ' + num(yp - HALF) + ' C' + num(xe) + ' ' + num(yp - HALF * 0.4) + ' ' + num(xp) + ' ' +
                num(yp - HALF * 0.6) + ' ' + num(xp) + ' ' + num(yp);
            }
          }
          paths += '<path class="gg-edge ' + col + '" d="' + p + '"/>';
        });
      });
      var dots = commits.map(function (c, r) {
        var merge = (c.parents || []).length > 1;
        var f = forks[r];
        var tip = c.author + ' · ' + c.ts + (c.branch ? ' · ' + c.branch : '') + '\n' + c.subject +
          (f ? '\nBranch point: ' + f.join(', ') + (f.length > 1 ? ' start' : ' starts') + ' on top of this commit' : '');
        var ring = f ? '<circle class="gg-fork gg-c' + branchColor[f[0]] + '" cx="' + num(cx(c.lane)) + '" cy="' + num(cy(r)) +
          '" r="' + (R + 5.5) + '"/>' : '';
        return ring + '<circle class="gg-dot gg-c' + colorOf(c) + (merge ? ' gg-merge' : '') + '" data-i="' + r + '" cx="' + num(cx(c.lane)) +
          '" cy="' + num(cy(r)) + '" r="' + R + '"><title>' + esc(tip) + '</title></circle>';
      }).join('');
      var svg = '<svg class="gg-svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H +
        '" role="img" aria-label="Branch graph of recent commits">' + paths + stubSvg + dots + '</svg>';

      // Branch names beside the graphic: a run of rows in one lane on one branch is a segment. Its newest row (the
      // tip, where the lane starts in the picture) gets the full chip; long segments repeat a faint chip so a row
      // in the middle can be read without scrolling back up. Commits with no known branch get no chip.
      var labelAt = {}, run = {}, lastRow = {};
      commits.forEach(function (c, r) {
        var b = c.branch || '';
        var seg = run[c.lane];
        if (!seg || seg.branch !== b) { seg = run[c.lane] = { branch: b, n: 0 }; }
        if (b && (seg.n === 0 || seg.n % 12 === 0)) labelAt[r] = seg.n === 0 ? 'tip' : 'more';
        seg.n++;
        lastRow[c.lane] = r;
        c._seg = seg;
      });
      commits.forEach(function (c, r) {
        // the oldest row of a long segment is where the branch splits off: label it too
        if (c._seg.branch && c._seg.n >= 5 && !labelAt[r] && lastRow[c.lane] === r) labelAt[r] = 'more';
      });
      function branchChip(c, r) {
        if (!labelAt[r]) return '<span class="gg-lbl-slot"></span>';
        return '<span class="gg-lbl-slot"><span class="gg-lbl gg-c' + colorOf(c) + (labelAt[r] === 'more' ? ' gg-lbl-more' : '') +
          '" title="' + esc(c.branch) + '">' + (c.branch.indexOf('feature/') === 0 ? '<span class="gg-lbl-pre">feature/</span>' + esc(c.branch.slice(8)) : esc(c.branch)) +
          '</span></span>';
      }

      var rows = commits.map(function (c, r) {
        var refs = (c.refs || []).filter(function (x) { return x !== c.branch || labelAt[r] !== 'tip'; }).map(refChip).join('');
        var hay = [c.subject, c.sha, c.short, c.author, c.branch || ''].concat(c.refs || []).join('\n').toLowerCase();
        return '<li class="gg-row" data-i="' + r + '" data-hay="' + esc(hay) + '">' + branchChip(c, r) +
          '<span class="gg-subject" title="' + esc(c.subject) + '">' + esc(c.subject) + '</span>' +
          (refs ? '<span class="gg-refs">' + refs + '</span>' : '') +
          '<span class="gg-sha mono">' + esc(c.short) + '</span>' +
          '<button type="button" class="hide-btn gg-copy" data-copy="' + esc(c.sha) + '">Copy</button>' +
          '<span class="gg-date mono">' + esc(stamp(c.ts)) + '</span>' +
          '<span class="gg-stat mono" title="' + esc(c.files + ' files') + '"><span class="git-ins">+' + esc(c.ins) +
          '</span>/<span class="git-del">-' + esc(c.del) + '</span></span></li>';
      }).join('');

      var total = d.window_commits || n;
      return '<p class="tok-note gg-note">Lanes follow the commit graph, exactly as <span class="mono">git log --graph</span> draws it: a branch that is ' +
        'built on top of another branch\'s newest commit stays in the same lane until something diverges or merges. Colour follows the branch; a ring marks a ' +
        'commit where another branch starts on top of it, and a hollow dot is a merge.' +
        (total > n ? ' Showing the newest ' + esc(n) + ' of ' + esc(total) + ' commits in the last ' + esc(days) + ' days.' : '') + '</p>' +
        '<div class="gg-bar"><input id="gitSearch" class="gg-search" type="search" placeholder="Filter by subject, sha, author or branch" ' +
        'aria-label="Filter commits"><span class="gg-count mono" id="ggCount">' + esc(n) + ' commits</span></div>' +
        '<div class="gg-body" style="--gg-h:' + H + 'px"><div class="gg-graph" style="width:' + W + 'px">' + svg + '</div>' +
        '<ol class="gg-rows">' + rows + '</ol></div>';
    }

    // ---- Active branches: what is in flight, and which features and stories each branch supports
    var VIA = { subject: 'commit subject', ledger: 'ledger', name: 'branch name', plan: 'plan branch field' };
    var SHOWN_LINKS = 6;
    function shortDate(ts) { return stamp(ts); }
    function storyChip(l) {
      return '<span class="ab-chip ab-story ab-via-' + esc(l.via) + '" title="' + esc(VIA[l.via] + ': ' + l.why) + '"><b class="mono">' +
        esc(l.s) + '</b> ' + esc(l.n) + '</span>';
    }
    function featChip(f) {
      return '<span class="ab-chip ab-feat ab-via-' + esc(f.via) + '" title="' + esc(VIA[f.via] + ': ' + f.why) + '">' + esc(f.n) + '</span>';
    }
    function branchRow(b) {
      var cnt = '';
      if (b.base && b.ahead != null) {
        cnt = '<span class="ab-cnt mono" title="Commits on this branch that ' + esc(b.base) + ' does not have (ahead), and the other way round (behind)">' +
          '<span class="git-ins">+' + esc(b.ahead) + '</span>/<span class="git-del">-' + esc(b.behind || 0) + '</span> vs ' + esc(b.base) + '</span>';
      }
      var pr = '';
      if (b.pr) pr = '<span class="ab-pr mono' + (b.pr.state === 'open' ? ' ab-pr-open' : '') + '" title="' +
        (b.pr.state === 'open' ? 'Open pull request (from gh at refresh time)' : 'Merged pull request (from the merge commit)') + '">PR #' + esc(b.pr.n) +
        ' ' + esc(b.pr.state) + '</span>';
      var state = b.merged ? '<span class="ab-state ab-merged-tag" title="Its newest commit is already in ' + esc(b.merged_into.join(', ')) + '">merged into ' +
        esc(b.merged_into[0]) + (b.merged_into.length > 1 ? ' +' + (b.merged_into.length - 1) : '') + '</span>'
        : (b.kind === 'base' ? '<span class="ab-state">base branch</span>' : '<span class="ab-state ab-open-tag">not merged</span>');
      var extra = '';
      if (b.stack) extra += '<span class="ab-note" title="Its own commits sit on top of that branch, which is not merged yet">on top of ' + esc(b.stack) + '</span>';
      if (b.same_tip && b.same_tip.length) extra += '<span class="ab-note" title="Both names point at the same commit">same tip as ' + esc(b.same_tip.join(', ')) + '</span>';
      if (b.own != null && b.kind === 'feature') extra += '<span class="ab-note mono" title="Commits only this branch has (not shared with a branch below it)">' + esc(b.own) + ' own</span>';
      var links = '';
      if (b.kind === 'base') {
        links = '<span class="ab-none">integration branch: carries many features, no single link</span>';
      } else if (!(b.links || []).length && !(b.features || []).length) {
        links = '<span class="ab-none ab-unlinked" title="No story id in its commit subjects, no ledger change while it was checked out, and its name matches no feature or story">unlinked</span>';
      } else {
        var ls = b.links || [], head = ls.slice(0, SHOWN_LINKS), rest = ls.slice(SHOWN_LINKS);
        links = (b.features || []).map(featChip).join('') + head.map(storyChip).join('') +
          (rest.length || b.more ? '<details class="ab-more"><summary>+' + esc(rest.length + (b.more || 0)) + ' more</summary>' + rest.map(storyChip).join('') +
            (b.more ? '<span class="ab-note">and ' + esc(b.more) + ' more stories not listed</span>' : '') + '</details>' : '');
      }
      return '<li class="ab-row' + (b.merged ? ' ab-merged' : '') + (b.head ? ' ab-head' : '') + '">' +
        '<div class="ab-top"><span class="ab-name mono" title="' + esc(b.name) + (b.local ? '' : ' (remote only)') + '">' + esc(b.name) + '</span>' +
        (b.head ? '<span class="ab-badge" title="The branch checked out in this repository">HEAD</span>' : '') + state +
        '<span class="ab-date mono" title="Newest commit on the branch">' + esc(shortDate(b.ts)) + '</span>' + cnt + pr + extra + '</div>' +
        '<div class="ab-links">' + links + '</div></li>';
    }
    function activeSection() {
      var act = d.active || {}, list = act.branches || [];
      if (!list.length) return '<div class="empty-note">No active branches in the data. Run <span class="mono">roadmap.py git</span> and reload.</div>';
      var open = list.filter(function (b) { return !b.merged; }), done = list.filter(function (b) { return b.merged; });
      var rule = '<p class="tok-note ab-rule">Active = not yet merged into a base branch (main, dev or a phase branch), or committed on in the last ' +
        esc(act.days || days) + ' days.' + (act.base ? ' Base for feature branches: <span class="mono">' + esc(act.base) + '</span>.' : '') +
        ' Hover a story or feature for how the link was found: commit subject, ledger or branch name.</p>';
      return rule + '<ul class="ab-list">' + open.map(branchRow).join('') + '</ul>' +
        (done.length ? '<h3 class="ab-sub">Merged, but committed on in the last ' + esc(act.days || days) + ' days (' + esc(done.length) + ')</h3><ul class="ab-list">' +
          done.map(branchRow).join('') + '</ul>' : '');
    }

    root.innerHTML =
      '<div class="git-tab">' +
      '<div class="git-chips">' + chip('commits', totals.commits || 0) + chip('merges', totals.merges || 0) +
      chip('branches', branches.length) + chip('days', days) + '</div>' +
      '<section class="git-sec"><h2 class="git-h">Active branches (' + esc(((d.active || {}).branches || []).length) + ')</h2>' + activeSection() + '</section>' +
      '<section class="git-sec"><h2 class="git-h">Commits per day</h2>' + bars() + '</section>' +
      '<section class="git-sec"><h2 class="git-h">History</h2>' + history() + '</section>' +
      '<section class="git-sec"><details class="gg-events"><summary>Branch events (' + esc(events.length) + ')</summary>' +
      eventList() + '</details></section>' +
      '<p class="tok-note">Older activity is archived, not loaded.</p></div>';

    var search = root.querySelector('#gitSearch');
    if (search) {
      var rowEls = root.querySelectorAll('.gg-row');
      var dotEls = root.querySelectorAll('.gg-dot');
      var count = root.querySelector('#ggCount');
      search.addEventListener('input', function () {
        var q = search.value.trim().toLowerCase(), hits = 0;
        for (var i = 0; i < rowEls.length; i++) {
          var hit = !q || rowEls[i].getAttribute('data-hay').indexOf(q) >= 0;
          if (hit) hits++;
          rowEls[i].classList.toggle('gg-dim', !hit);
          if (dotEls[i]) dotEls[i].classList.toggle('gg-dim', !hit);
        }
        count.textContent = q ? hits + ' of ' + rowEls.length + ' commits' : rowEls.length + ' commits';
      });
    }
    root.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-copy]') : null;
      if (!btn) return;
      RM.copy(btn.getAttribute('data-copy'));
      btn.textContent = 'Copied';
      setTimeout(function () { btn.textContent = 'Copy'; }, 1200);
    });
  }

  RM.tabs.git = { mount: mount };
})();
