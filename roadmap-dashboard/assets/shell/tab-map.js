/* Project map tab: districts of files, grouped under subheadings, in inline SVG. Select a file to see its relations and details. */
(function () {
  'use strict';
  var RM = window.RM;
  var esc = RM.esc;

  var HUES = { teal: '--teal', gold: '--gold', blue: '--blue', green: '--green', coral: '--coral', slate: '--slate', purple: '--status-planning' };
  var RELS = {
    'mentions': { out: 'Mentions', inn: 'Mentioned by', color: 'var(--accent)' },
    'declares': { out: 'Declares', inn: 'Declared by', color: 'var(--accent-2)' },
    'based-on': { out: 'Based on', inn: 'Base of', color: 'var(--status-planning)' }
  };
  var CELL_W = 176, CELL_H = 32, PILL_W = 168, PILL_H = 26, GHEAD = 26, PAD = 14, GAP = 14, HEAD = 50, MIN_COL = 340;
  function fmtSize(b) {
    b = Number(b) || 0;
    return b < 1024 ? b + ' B' : (b / 1024).toFixed(b < 10240 ? 1 : 0) + ' KB';
  }
  function ageDays(iso) {
    var t = Date.parse(iso);
    return isNaN(t) ? null : (Date.now() - t) / 864e5;
  }
  function fmtAge(iso) {
    var d = ageDays(iso);
    if (d == null) return 'age unknown';
    if (d < 1) return 'today';
    if (d < 30) return Math.floor(d) + 'd ago';
    if (d < 365) return Math.floor(d / 30) + 'mo ago';
    return Math.floor(d / 365) + 'y ago';
  }
  function trunc(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, Math.max(1, n - 1)) + '\u2026' : s; }
  function isSecret(n) { return n.kind === 'secret'; }

  function mount(root, data) {
    var m = data && data.map;
    if (!m || !Array.isArray(m.nodes)) {
      root.innerHTML = '<div class="error-box"><b>map.json</b> has no file list. Run <span class="mono">roadmap.py map</span> and publish again.</div>';
      return;
    }
    if (!m.nodes.length) {
      root.innerHTML = '<div class="empty-note">The project map is empty. Run <span class="mono">roadmap.py map</span> to scan the project.</div>';
      return;
    }

    var nodes = {}, districts = (m.districts || []).slice().sort(function (a, b) { return (a.order || 0) - (b.order || 0); });
    var known = {};
    districts.forEach(function (d) { known[d.id] = d; });
    m.nodes.forEach(function (n) {
      nodes[n.id] = n;
      if (!known[n.district]) { known[n.district] = { id: n.district, name: n.district || 'Other', blurb: '', order: 99, hue: 'slate' }; districts.push(known[n.district]); }
    });
    var byDistrict = {};
    m.nodes.forEach(function (n) { (byDistrict[n.district] = byDistrict[n.district] || []).push(n); });
    var outMap = {}, inMap = {};
    (m.relations || []).forEach(function (r) {
      if (!nodes[r.from] || !nodes[r.to] || r.from === r.to) return;
      (outMap[r.from] = outMap[r.from] || []).push(r);
      (inMap[r.to] = inMap[r.to] || []).push(r);
    });

    var sel = null, q = '', hidden = {}, rove = null, W = 0, H = 0;
    var base = { x: 0, y: 0, w: 1, h: 1 }, vb = { x: 0, y: 0, w: 1, h: 1 };
    var pos = {}, els = {}, matches = null, svg = null;

    function hueVar(d) { return 'var(' + (HUES[d.hue] || '--slate') + ')'; }

    root.innerHTML =
      '<div class="map-tab"><div class="map-bar">' +
      '<input class="map-search" type="search" placeholder="Search files" aria-label="Search files">' +
      '<span class="map-count mono" aria-live="polite"></span>' +
      '<span class="map-zoom"><button type="button" class="map-btn" data-z="in" aria-label="Zoom in">+</button>' +
      '<button type="button" class="map-btn" data-z="out" aria-label="Zoom out">\u2212</button>' +
      '<button type="button" class="map-btn" data-z="reset" aria-label="Reset zoom">Reset</button></span></div>' +
      '<div class="map-chips" role="group" aria-label="Show or hide districts">' + districts.map(function (d) {
        return '<button type="button" class="map-chip" data-d="' + esc(d.id) + '" aria-pressed="true" style="--dh:' + hueVar(d) + '"><i></i>' +
          esc(d.name) + ' <span class="mono">' + (byDistrict[d.id] || []).length + '</span></button>';
      }).join('') + '</div>' +
      '<p class="map-hint">Ctrl or Cmd + mouse wheel zooms the map, drag pans it, arrow keys move between files, Enter selects, Esc clears. Lines appear only for the selected file.</p>' +
      '<div class="map-body"><div class="map-stage"><div class="map-canvas"></div><div class="map-tip" role="tooltip" hidden></div></div>' +
      '<aside class="map-detail empty" aria-label="File details"></aside></div></div>';

    var tab = root.querySelector('.map-tab');
    var holder = root.querySelector('.map-canvas');
    var tip = root.querySelector('.map-tip');
    var detail = root.querySelector('.map-detail');
    var countEl = root.querySelector('.map-count');
    var search = root.querySelector('.map-search');

    // ---- layout and drawing
    // files of a district, split into labelled groups (a district whose files have no group is drawn flat)
    function groupsOf(d) {
      var list = byDistrict[d.id] || [], map = {}, out = [];
      list.forEach(function (n) {
        var g = n.group || '';
        if (!map[g]) { map[g] = { name: g, order: n.gorder == null ? 99 : n.gorder, items: [] }; out.push(map[g]); }
        map[g].order = Math.min(map[g].order, n.gorder == null ? 99 : n.gorder);
        map[g].items.push(n);
      });
      out.sort(function (a, b) { return a.order - b.order || (a.name < b.name ? -1 : 1); });
      return out;
    }

    function layout() {
      var w = holder.clientWidth || 800;
      W = w;
      var phone = window.matchMedia && window.matchMedia('(max-width:640px)').matches;
      var vis = districts.filter(function (d) { return !hidden[d.id]; });
      var cols = phone ? 1 : Math.max(1, Math.floor(w / MIN_COL));
      var colW = (w - (cols - 1) * GAP) / cols;
      var perRow = Math.max(1, Math.floor((colW - 2 * PAD) / CELL_W));
      var out = [], colY = [];
      for (var c0 = 0; c0 < cols; c0++) colY.push(0);
      pos = {};
      // masonry: each district goes into the shortest column, so tall and short districts pack together
      vis.forEach(function (d) {
        var c = 0;
        for (var k0 = 1; k0 < cols; k0++) if (colY[k0] < colY[c]) c = k0;
        var y = colY[c], x = c * (colW + GAP), cy = y + HEAD, items = [], heads = [];
        groupsOf(d).forEach(function (g) {
          if (g.name) { heads.push({ name: g.name, count: g.items.length, x: x + PAD, y: cy }); cy += GHEAD; }
          g.items.forEach(function (n, k) {
            var tx = x + PAD + (k % perRow) * CELL_W, ty = cy + Math.floor(k / perRow) * CELL_H;
            pos[n.id] = { cx: tx + PILL_W / 2, cy: ty + PILL_H / 2 };
            items.push({ n: n, x: tx, y: ty });
          });
          cy += Math.ceil(g.items.length / perRow) * CELL_H + (g.name ? 6 : 0);
        });
        var h = Math.max(HEAD + CELL_H, cy - y) + PAD;
        out.push({ d: d, x: x, y: y, w: colW, h: h, items: items, heads: heads });
        colY[c] = y + h + GAP;
      });
      var y = Math.max.apply(null, colY.concat([0]));
      H = vis.length ? Math.max(60, y - GAP) : 70;
      return out;
    }

    function tileHtml(it, d) {
      var n = it.n, age = ageDays(n.modified), lit = age != null && age <= 7;
      var label = n.name + ', ' + n.kind + (isSecret(n) ? ', never read' : ', ' + fmtSize(n.bytes) + ', ' + fmtAge(n.modified)) +
        (lit ? ', recently modified' : '');
      return '<g class="mb" role="button" tabindex="-1" aria-pressed="false" data-id="' + esc(n.id) + '" aria-label="' + esc(label) +
        '" style="--dh:' + hueVar(d) + '" transform="translate(' + it.x + ' ' + it.y + ')">' +
        '<rect class="mt" x="0" y="0" width="' + PILL_W + '" height="' + PILL_H + '" rx="7"/>' +
        (lit ? '<circle class="lit" cx="11" cy="' + PILL_H / 2 + '" r="2.8"/>' : '') +
        '<text x="' + (lit ? 21 : 10) + '" y="' + (PILL_H / 2 + 3.5) + '">' + esc(trunc(n.name, lit ? 26 : 28)) + '</text></g>';
    }

    function render() {
      var laid = layout();
      var panels = '', tiles = '';
      laid.forEach(function (L) {
        var d = L.d, st = 'style="--dh:' + hueVar(d) + '"';
        var maxc = Math.floor((L.w - 2 * PAD) / 6);
        panels += '<g class="md" ' + st + '><rect class="md-panel" x="' + L.x + '" y="' + L.y + '" width="' + L.w + '" height="' + L.h + '" rx="14"/>' +
          '<rect class="md-bar" x="' + (L.x + PAD) + '" y="' + (L.y + 12) + '" width="4" height="28" rx="2"/>' +
          '<text class="md-name" x="' + (L.x + PAD + 12) + '" y="' + (L.y + 23) + '">' + esc(trunc(d.name, maxc - 6)) + '</text>' +
          '<text class="md-sub" x="' + (L.x + PAD + 12) + '" y="' + (L.y + 38) + '">' + esc(trunc(d.blurb, maxc - 2)) + '</text>' +
          L.heads.map(function (g) {
            return '<text class="mg-h" x="' + g.x + '" y="' + (g.y + 15) + '">' + esc(trunc(g.name, maxc - 4)) + ' <tspan class="mg-n">' + g.count + '</tspan></text>';
          }).join('') +
          (L.items.length ? '' : '<text class="md-sub" x="' + (L.x + PAD) + '" y="' + (L.y + HEAD + 24) + '">No files here.</text>') + '</g>';
        L.items.forEach(function (it) { tiles += tileHtml(it, d); });
      });
      var empty = laid.length ? '' : '<text class="md-sub" x="16" y="38">All districts are hidden. Use the chips above to show one.</text>';
      base = { x: 0, y: 0, w: W, h: H };
      vb = { x: 0, y: 0, w: W, h: H };
      holder.innerHTML = '<svg class="map-svg" viewBox="0 0 ' + W + ' ' + H + '" style="height:' + Math.round(H) + 'px" role="group" aria-label="Project map">' +
        '<g class="dl">' + panels + empty + '</g><g class="bl">' + tiles + '</g><g class="rl"></g></svg>';
      svg = holder.firstChild;
      els = {};
      Array.prototype.forEach.call(svg.querySelectorAll('.mb'), function (e) { els[e.getAttribute('data-id')] = e; });
      if (sel && !els[sel]) sel = null;
      if (!rove || !els[rove]) rove = sel || firstVisible();
      if (rove && els[rove]) els[rove].setAttribute('tabindex', '0');
      holder.classList.remove('zoomed');
      hideTip();
      refresh();
    }

    function firstVisible() {
      for (var i = 0; i < districts.length; i++) {
        var l = byDistrict[districts[i].id];
        if (!hidden[districts[i].id] && l && l.length) return l[0].id;
      }
      return null;
    }

    // ---- state -> DOM
    function relatedIds(id) {
      var s = {};
      (outMap[id] || []).forEach(function (r) { s[r.to] = 1; });
      (inMap[id] || []).forEach(function (r) { s[r.from] = 1; });
      return s;
    }

    function computeMatches() {
      if (!q) { matches = null; return; }
      matches = {};
      var t = q.toLowerCase();
      m.nodes.forEach(function (n) {
        var hay = (n.name + ' ' + n.id + ' ' + n.kind + ' ' + (isSecret(n) ? '' : (n.path || '') + ' ' + (n.desc || ''))).toLowerCase();
        if (hay.indexOf(t) >= 0) matches[n.id] = 1;
      });
    }

    function refresh() {
      var rel = sel ? relatedIds(sel) : null, lit = 0, total = 0;
      Object.keys(els).forEach(function (id) {
        var e = els[id];
        var off = matches && !matches[id];
        total++;
        if (!off) lit++;
        e.classList.toggle('dim', !!(off || (sel && id !== sel && !rel[id])));
        e.classList.toggle('sel', id === sel);
        e.classList.toggle('rel', !!(sel && rel[id]));
        e.setAttribute('aria-pressed', id === sel ? 'true' : 'false');
      });
      countEl.textContent = matches ? lit + ' of ' + total + ' match' : total + ' files';
      drawRel();
      renderDetail();
      tab.classList.toggle('has-sel', !!sel);
    }

    function drawRel() {
      var layer = svg.querySelector('.rl');
      if (!sel) { layer.innerHTML = ''; return; }
      var out = '';
      (outMap[sel] || []).concat(inMap[sel] || []).forEach(function (r) {
        var a = pos[r.from], b = pos[r.to];
        if (!a || !b) return;
        var mx = (a.cx + b.cx) / 2, my = (a.cy + b.cy) / 2;
        var dx = b.cx - a.cx, dy = b.cy - a.cy, len = Math.sqrt(dx * dx + dy * dy) || 1;
        var off = Math.min(70, len * 0.2);
        var qx = mx - dy / len * off, qy = my + dx / len * off;
        var info = RELS[r.kind] || { color: 'var(--text-secondary)' };
        out += '<path class="rel-line k-' + esc(r.kind) + '" style="stroke:' + info.color + '" d="M' + a.cx.toFixed(1) + ' ' + a.cy.toFixed(1) +
          ' Q' + qx.toFixed(1) + ' ' + qy.toFixed(1) + ' ' + b.cx.toFixed(1) + ' ' + b.cy.toFixed(1) + '"/>' +
          '<circle class="rel-dot" style="fill:' + info.color + '" cx="' + b.cx.toFixed(1) + '" cy="' + b.cy.toFixed(1) + '" r="3.5"/>';
      });
      layer.innerHTML = out;
    }

    function renderDetail() {
      detail.classList.toggle('empty', !sel);
      if (!sel) {
        detail.innerHTML = '<p class="map-muted">Select a file to see its description, path and relations.</p>';
        return;
      }
      var n = nodes[sel], d = known[n.district] || {}, secret = isSecret(n);
      var h = '<div class="map-dh"><div><h3>' + esc(n.name) + '</h3><div class="map-kind mono">' + esc(n.kind) + ' \u00b7 ' + esc(d.name || '') +
        '</div></div><button type="button" class="hide-btn map-close" data-close="1" aria-label="Close details">Close</button></div>';
      if (secret) {
        h += '<p class="map-never">Never read</p><p class="map-muted">This file exists so its presence is visible. Its contents are never opened, shown or measured.</p>';
      } else {
        h += '<p class="map-desc">' + esc(n.desc || 'No description.') + '</p>';
        if (n.path) h += '<div class="map-row"><span class="map-k">Path</span><span class="mono map-path">' + esc(n.path) +
          '</span><button type="button" class="hide-btn" data-copy="' + esc(n.path) + '">Copy</button></div>';
        if (n.bytes != null) h += '<div class="map-row"><span class="map-k">Size</span><span class="mono">' + esc(fmtSize(n.bytes)) + '</span></div>';
        if (n.modified) h += '<div class="map-row"><span class="map-k">Modified</span><span class="mono">' + esc(RM.fmtDate(n.modified)) +
          ' (' + esc(fmtAge(n.modified)) + ')</span></div>';
        var meta = n.meta || {}, mk = Object.keys(meta).filter(function (k) { return meta[k] !== '' && meta[k] != null; });
        if (mk.length) h += '<div class="map-chipsrow">' + mk.map(function (k) {
          return '<span class="git-ref mono">' + esc(k) + ': ' + esc(meta[k]) + '</span>';
        }).join('') + '</div>';
        var ch = n.children || [];
        if (ch.length) h += '<h4 class="map-h">Files (' + ch.length + ')</h4><ul class="map-files">' + ch.slice(0, 40).map(function (c) {
          return '<li><span class="mono">' + esc(c.name) + '</span><span class="mono map-muted">' + esc(fmtSize(c.bytes)) + '</span></li>';
        }).join('') + '</ul>' + (ch.length > 40 ? '<p class="map-muted">Showing 40 of ' + ch.length + '.</p>' : '');
      }
      var kinds = {};
      (outMap[sel] || []).concat(inMap[sel] || []).forEach(function (r) { kinds[r.kind] = 1; });
      var relHtml = '';
      Object.keys(kinds).sort().forEach(function (k) {
        var info = RELS[k] || { out: k, inn: k + ' (reverse)', color: 'var(--text-secondary)' };
        [['out', outMap[sel], 'to'], ['inn', inMap[sel], 'from']].forEach(function (g) {
          var list = (g[1] || []).filter(function (r) { return r.kind === k; });
          if (!list.length) return;
          relHtml += '<div class="map-relgrp"><div class="map-relh"><i style="background:' + info.color + '"></i>' + esc(info[g[0]]) + ' (' + list.length + ')</div>' +
            list.map(function (r) {
              var o = nodes[r[g[2]]];
              return '<button type="button" class="map-rel" data-go="' + esc(o.id) + '">' + esc(o.name) + '</button>';
            }).join('') + '</div>';
        });
      });
      h += '<h4 class="map-h">Related</h4>' + (relHtml || '<p class="map-muted">No relations recorded.</p>');
      var links = secret ? [] : (n.links || []).filter(function (l) { return l && /^https:\/\//i.test(String(l.href)); });
      if (links.length) h += '<h4 class="map-h">Links</h4><div class="map-links">' + links.map(function (l) {
        return '<a class="map-link" href="' + esc(l.href) + '" target="_blank" rel="noopener noreferrer">' + esc(l.label || l.href) + '</a>';
      }).join('') + '</div>';
      detail.innerHTML = h;
      detail.scrollTop = 0;
    }

    function reduced() { return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; }

    function select(id, opts) {
      opts = opts || {};
      if (id && !nodes[id]) return;
      sel = id;
      if (id && hidden[nodes[id].district]) { hidden[nodes[id].district] = false; syncChips(); render(); }
      else refresh();
      if (id) setRove(id);
      if (id && opts.focus && els[id]) {
        reveal(id);
        try { els[id].focus({ preventScroll: true }); } catch (e) { els[id].focus(); }
        if (opts.scroll) els[id].scrollIntoView({ block: 'center', behavior: reduced() ? 'auto' : 'smooth' });
      }
    }

    function setRove(id) {
      if (rove && els[rove]) els[rove].setAttribute('tabindex', '-1');
      rove = id;
      if (els[id]) els[id].setAttribute('tabindex', '0');
    }

    function syncChips() {
      Array.prototype.forEach.call(root.querySelectorAll('.map-chip'), function (c) {
        c.setAttribute('aria-pressed', hidden[c.getAttribute('data-d')] ? 'false' : 'true');
      });
    }

    // ---- viewBox zoom and pan
    function applyVB() {
      vb.w = Math.max(base.w / 6, Math.min(base.w, vb.w));
      vb.h = vb.w * base.h / base.w;
      vb.x = Math.max(base.x, Math.min(base.x + base.w - vb.w, vb.x));
      vb.y = Math.max(base.y, Math.min(base.y + base.h - vb.h, vb.y));
      svg.setAttribute('viewBox', vb.x.toFixed(1) + ' ' + vb.y.toFixed(1) + ' ' + vb.w.toFixed(1) + ' ' + vb.h.toFixed(1));
      holder.classList.toggle('zoomed', vb.w < base.w - 0.5);
      hideTip();
    }
    function zoomAt(f, cx, cy) {
      var nw = Math.max(base.w / 6, Math.min(base.w, vb.w / f));
      var k = nw / vb.w;
      vb.x = cx - (cx - vb.x) * k;
      vb.y = cy - (cy - vb.y) * k;
      vb.w = nw;
      applyVB();
    }
    function reveal(id) {
      var p = pos[id];
      if (!p) return;
      if (p.cx < vb.x + 30 || p.cx > vb.x + vb.w - 30 || p.cy < vb.y + 30 || p.cy > vb.y + vb.h - 30) {
        vb.x = p.cx - vb.w / 2; vb.y = p.cy - vb.h / 2; applyVB();
      }
    }
    function toWorld(ev) {
      var r = svg.getBoundingClientRect();
      return { x: vb.x + (ev.clientX - r.left) / r.width * vb.w, y: vb.y + (ev.clientY - r.top) / r.height * vb.h };
    }

    // ---- tooltip
    function showTip(e, x, y) {
      var n = nodes[e.getAttribute('data-id')];
      if (!n) return;
      tip.innerHTML = '<b>' + esc(n.name) + '</b><br><span class="mono">' + esc(n.kind) + ' \u00b7 ' +
        (isSecret(n) ? 'Never read' : esc(fmtSize(n.bytes)) + ' \u00b7 ' + esc(fmtAge(n.modified))) + '</span>';
      tip.hidden = false;
      var sr = holder.getBoundingClientRect();
      var px = Math.max(4, Math.min(sr.width - tip.offsetWidth - 4, x - sr.left + 12));
      tip.style.left = px + 'px'; tip.style.top = (y - sr.top + 14) + 'px';
    }
    function hideTip() { tip.hidden = true; }

    // ---- events
    var drag = null, moved = false;
    holder.addEventListener('click', function (ev) {
      if (moved) { moved = false; return; }
      var b = ev.target.closest ? ev.target.closest('.mb') : null;
      if (b) select(b.getAttribute('data-id'));
      else if (sel) select(null);
    });
    holder.addEventListener('keydown', function (ev) {
      var b = ev.target.closest ? ev.target.closest('.mb') : null;
      if (!b) return;
      var id = b.getAttribute('data-id');
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select(id); return; }
      var dir = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[ev.key];
      if (!dir) return;
      ev.preventDefault();
      var p = pos[id], best = null, bs = 1e12;
      Object.keys(els).forEach(function (o) {
        if (o === id) return;
        var q2 = pos[o], dx = q2.cx - p.cx, dy = q2.cy - p.cy;
        var along = dx * dir[0] + dy * dir[1], perp = Math.abs(dx * dir[1]) + Math.abs(dy * dir[0]);
        if (along < 10) return;
        var s = along + 2.5 * perp;
        if (s < bs) { bs = s; best = o; }
      });
      if (best) { setRove(best); reveal(best); els[best].focus({ preventScroll: true }); }
    });
    holder.addEventListener('focusin', function (ev) {
      var b = ev.target.closest ? ev.target.closest('.mb') : null;
      if (!b) return;
      setRove(b.getAttribute('data-id'));
      if (b.matches && b.matches(':focus-visible')) {
        var r = b.getBoundingClientRect();
        showTip(b, r.left + r.width / 2 - 40, r.bottom - 10);
      }
    });
    holder.addEventListener('focusout', hideTip);
    holder.addEventListener('pointerover', function (ev) {
      var b = ev.target.closest ? ev.target.closest('.mb') : null;
      if (b && !drag) showTip(b, ev.clientX, ev.clientY); else if (!b) hideTip();
    });
    holder.addEventListener('pointermove', function (ev) {
      if (drag) {
        var dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
        if (!moved && Math.abs(dx) + Math.abs(dy) > 4) {
          moved = true;
          try { holder.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
          hideTip();
        }
        if (moved) {
          var r = svg.getBoundingClientRect(), k = drag.vb.w / r.width;
          vb.x = drag.vb.x - dx * k; vb.y = drag.vb.y - dy * k;
          applyVB();
        }
        return;
      }
      var b = ev.target.closest ? ev.target.closest('.mb') : null;
      if (b) showTip(b, ev.clientX, ev.clientY);
    });
    holder.addEventListener('pointerleave', hideTip);
    holder.addEventListener('pointerdown', function (ev) {
      if (ev.button !== 0) return;
      if (ev.pointerType === 'touch' && vb.w >= base.w - 0.5) return;
      drag = { x: ev.clientX, y: ev.clientY, vb: { x: vb.x, y: vb.y, w: vb.w } };
      moved = false;
    });
    function endDrag(ev) {
      if (!drag) return;
      drag = null;
      try { holder.releasePointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
      if (moved) setTimeout(function () { moved = false; }, 0);
    }
    holder.addEventListener('pointerup', endDrag);
    holder.addEventListener('pointercancel', endDrag);
    holder.addEventListener('wheel', function (ev) {
      if (!(ev.ctrlKey || ev.metaKey)) return;
      ev.preventDefault();
      var w = toWorld(ev);
      zoomAt(ev.deltaY < 0 ? 1.15 : 1 / 1.15, w.x, w.y);
    }, { passive: false });

    root.addEventListener('click', function (ev) {
      var t = ev.target.closest ? ev.target.closest('button') : null;
      if (!t) return;
      var z = t.getAttribute('data-z'), dsel = t.getAttribute('data-d'), go = t.getAttribute('data-go');
      if (z) {
        if (z === 'reset') { vb = { x: base.x, y: base.y, w: base.w, h: base.h }; applyVB(); }
        else zoomAt(z === 'in' ? 1.3 : 1 / 1.3, vb.x + vb.w / 2, vb.y + vb.h / 2);
      } else if (dsel) {
        hidden[dsel] = !hidden[dsel];
        t.setAttribute('aria-pressed', hidden[dsel] ? 'false' : 'true');
        render();
      } else if (go) {
        select(go, { focus: true, scroll: true });
      } else if (t.hasAttribute('data-close')) {
        select(null);
      } else if (t.hasAttribute('data-copy')) {
        RM.copy(t.getAttribute('data-copy'));
        t.textContent = 'Copied';
        setTimeout(function () { t.textContent = 'Copy'; }, 1200);
      }
    });
    root.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      if (sel) select(null);
      else if (ev.target === search && search.value) { search.value = ''; q = ''; computeMatches(); refresh(); }
    });
    search.addEventListener('input', function () { q = search.value.trim(); computeMatches(); refresh(); });

    var timer = null;
    function onSize() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var w = holder.clientWidth;
        if (w && Math.abs(w - W) > 1) render();
      }, 120);
    }
    if (window.ResizeObserver) new ResizeObserver(onSize).observe(holder);
    else window.addEventListener('resize', onSize);

    render();
  }

  RM.tabs.map = { mount: mount };
})();
