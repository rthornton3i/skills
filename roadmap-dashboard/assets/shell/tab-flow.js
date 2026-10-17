/* Execution flow tab: the ledger as a git-tree-style branch graph, story filter, shape key and the story details pane.
   flow.json is fetched when this tab opens (ctx.load), never before; plan.json and tokens.json (tab data) feed the
   details pane through RM.story (app.js), the same pane the Plan tab uses. */
(function () {
  'use strict';
  const RM = window.RM;
  const esc = RM.esc, fmtTok = RM.fmtTok;

  RM.tabs.flow = { mount(root, data, ctx) {
    const PLAN = data.plan || {};
    const TOK = data.tokens || {};
    const phases = PLAN.phases || [], features = PLAN.features || [], stories = PLAN.stories || [];
    const agents = PLAN.agents || {};
    let ARCH = null, archLoading = false, archError = '';
    let FLOW = null, flowLoading = false, flowError = '';

    root.innerHTML = '<div class="flow-tab" id="flowMain"></div>';
    const mainEl = root.querySelector('#flowMain');
    const statusMeta = RM.story.statusMeta;

    // the details pane needs the feature and phase of a story, including archived ones once plan-archive.json is loaded
    const allFeatures = () => features.concat(ARCH ? ARCH.features : []);
    const allPhases = () => phases.concat(ARCH ? ARCH.phases : []);
    const featureOf = id => allFeatures().find(f => f.id === id) || { id, name:id, phase:'' };
    const phaseOf = id => allPhases().find(p => p.id === id) || { id, name:id };
    const env = { agents, tokens:TOK, featureOf, phaseOf, isHidden: () => false };

    // ---- execution flow: the ledger as a branch graph (newest at the top), loaded lazily from flow.json (its own tab) ----
    const FL = { ROW:30, LANE:16, PAD:14 };
    const ROLE = { 'planning':'Planner', 'plan-review':'Plan critic', 'progress':'Implementer', 'review':'Review critic',
      'approval':'Approval', 'done':'Closed', 'not-started':'Reset to queue' };
    const flowStamp = ts => { const d = new Date(String(ts).slice(0, 19) + 'Z'); return isNaN(d) ? String(ts) : d.toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', hourCycle:'h23' }).replace(',', ''); };
    // tokens per step, compact like the rest of the page: 950, 1.2k, 152k, 1.2M ("-" when no run is recorded for the step)
    const flowTok = n => n > 0 ? fmtTok(n) : '-';
    // columns, left to right, after the graph; the same classes style the header cell and the row cell
    const FLOW_COLS = [['phase', 'Phase'], ['feat', 'Feature'], ['story', 'Story'], ['step', 'Step in flow'], ['agent', 'Agent'], ['tok', 'Tokens'], ['date', 'Date-time']];
    const fnum = n => Math.round(n * 10) / 10;
    // one neutral line color; an accent marks a story that is still open. The stage entered is told by the point's SHAPE.
    const FLOW_KEY = [['planning', 'Planning'], ['plan-review', 'Plan critique'], ['progress', 'Implementing'], ['review', 'Review'],
      ['approval', 'Approval'], ['done', 'Done (merged)']];
    function shapeD(state, x, y){
      const f = fnum;
      switch(state){
        case 'plan-review': return `M${f(x)} ${f(y - 6)}L${f(x + 6)} ${f(y)}L${f(x)} ${f(y + 6)}L${f(x - 6)} ${f(y)}Z`;
        case 'progress':    return `M${f(x - 4)} ${f(y - 4)}h8v8h-8Z`;
        case 'review':      return `M${f(x)} ${f(y - 5.5)}L${f(x + 5.5)} ${f(y + 4)}L${f(x - 5.5)} ${f(y + 4)}Z`;
        case 'approval':    return `M${f(x + 5.2)} ${f(y)}L${f(x + 2.6)} ${f(y + 4.5)}L${f(x - 2.6)} ${f(y + 4.5)}L${f(x - 5.2)} ${f(y)}L${f(x - 2.6)} ${f(y - 4.5)}L${f(x + 2.6)} ${f(y - 4.5)}Z`;
        case 'not-started': return `M${f(x - 2.5)} ${f(y)}a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0Z`;
        default:            return `M${f(x - 4.5)} ${f(y)}a4.5 4.5 0 1 0 9 0a4.5 4.5 0 1 0-9 0Z`;  // planning, done: circle
      }
    }
    const shapeKey = FLOW_KEY.map(([st, label]) =>
      `<span class="fl-key"><svg class="fl-shape" width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true"><path class="gg-dot${st === 'done' ? ' gg-merge' : ''}" style="--gc:var(--text-secondary)" d="${shapeD(st, 0, 0)}"/></svg>${esc(label)}</span>`).join('');

    // flow UI state (kept for the session only)
    const flowSel = new Set();          // story ids chosen in the filter; empty = show everything
    let flowPanelOpen = false, flowQuery = '', flowOne = null;   // panel open, panel search text, story whose details are open

    function loadFlow(){
      if(FLOW || flowLoading) return;
      flowLoading = true; flowError = '';
      ctx.load('flow').then(f => { FLOW = f; }).catch(e => { flowError = String(e && e.message || e) + '.'; })
        .then(() => { flowLoading = false; renderFlow(); });
    }
    // archived stories live in plan-archive.json, fetched only when one of them is opened
    function loadArchive(){
      if(ARCH || archLoading) return;
      archLoading = true; archError = '';
      ctx.load('archive').then(a => {
        ARCH = { phases:a.phases || [], features:a.features || [],
          stories:(a.stories || []).map(s => Object.assign({ status:'done', archived:true }, s)) };
      }).catch(e => { archError = String(e && e.message || e) + '.'; })
        .then(() => { archLoading = false; if(FLOW && flowOne) renderFlowBody(); });
    }

    // Lanes are packed on the page so a filter leaves no gaps (same rule as rm_flow.py assign_lanes): a lane is reused
    // only when the earlier story is completely finished; an open story keeps its lane up to the top edge.
    function packLanes(rows){
      const info = {}, n = rows.length;
      rows.forEach((r, i) => { const s = info[r.story] || (info[r.story] = { top:i, bottom:i }); s.bottom = i; });
      Object.keys(info).forEach(sid => { const s = info[sid]; s.closed = rows[s.top].state === 'done'; if((FLOW.stories[sid] || {}).cut) s.bottom = n; });
      const frontier = [], lane = {};
      Object.keys(info).sort((a, b) => (info[b].bottom - info[a].bottom) || (a < b ? -1 : a > b ? 1 : 0)).forEach(sid => {
        const s = info[sid], occ = s.closed ? s.top : 0, i = frontier.findIndex(top => s.bottom < top);
        if(i >= 0){ frontier[i] = occ; lane[sid] = i + 1; } else { frontier.push(occ); lane[sid] = frontier.length; }
      });
      return { lane, count:frontier.length };
    }

    function flowGraph(rows){
      const HALF = FL.ROW / 2, n = rows.length, pk = packLanes(rows), lanes = Math.max(1, pk.count) + 1;
      const W = FL.PAD + (lanes - 1) * FL.LANE + 14, H = n * FL.ROW;
      const cx = l => FL.PAD + l * FL.LANE, cy = r => r * FL.ROW + HALF;
      const by = {};
      rows.forEach((r, i) => { (by[r.story] = by[r.story] || []).push(i); });
      const x0 = cx(0);
      let edges = '', dots = '', stubs = '';
      Object.keys(by).forEach(sid => {
        const st = FLOW.stories[sid] || {}, list = by[sid], top = list[0];
        const xl = cx(Math.max(1, pk.lane[sid] | 0)), done = rows[top].state === 'done';
        const col = done ? 'var(--text-secondary)' : 'var(--accent)', on = flowOne === sid ? ' fl-sel' : '', fs = `data-fsid="${esc(sid)}"`;
        const nodes = done ? list.slice(1) : list;
        const line = (ya, yb, cls) => `<path class="gg-edge${cls || ''}${on}" style="--gc:${col}" d="M${xl} ${fnum(ya)} L${xl} ${fnum(yb)}"/>`;
        const tip = r => `${rows[r].ts.replace('T', ' ')} UTC · ${sid} · ${ROLE[rows[r].state] || rows[r].state}${rows[r].agent ? ' · ' + rows[r].agent : ''}`;
        if(done){
          const y1 = cy(top);
          edges += `<path class="gg-edge${on}" style="--gc:${col}" d="M${x0} ${fnum(y1)} C${x0} ${fnum(y1 + HALF * 0.6)} ${xl} ${fnum(y1 + HALF * 0.4)} ${xl} ${fnum(y1 + HALF)}"/>`;
          if(nodes.length) edges += line(y1 + HALF, cy(nodes[0]));
          dots += `<path class="gg-dot gg-merge${on}" ${fs} style="--gc:${col}" d="${shapeD('done', x0, fnum(y1))}"><title>${esc(tip(top))} · merged to main</title></path>`;
        }
        for(let k = 0; k < nodes.length - 1; k++) edges += line(cy(nodes[k]), cy(nodes[k + 1]), rows[nodes[k]].loop > 1 ? ' fl-loop' : '');
        if(nodes.length){
          const last = nodes[nodes.length - 1], yl = cy(last);
          if(st.cut){
            edges += line(yl, H - 7);
            stubs += `<circle class="gg-stub" style="--gc:${col}" cx="${xl}" cy="${H - 4}" r="3"><title>older history not loaded</title></circle>`;
          } else {
            edges += `<path class="gg-edge${on}" style="--gc:${col}" d="M${xl} ${fnum(yl)} C${xl} ${fnum(yl + HALF * 0.6)} ${x0} ${fnum(yl + HALF * 0.4)} ${x0} ${fnum(yl + HALF)}"/>`;
          }
          nodes.forEach(r => { dots += `<path class="gg-dot${on}" ${fs} style="--gc:${col}" d="${shapeD(rows[r].state, xl, cy(r))}"><title>${esc(tip(r))}</title></path>`; });
          if(!done) dots += `<circle class="fl-halo" style="--gc:${col}" cx="${xl}" cy="${fnum(cy(top))}" r="9"/>`;
        }
      });
      return { W, H, svg: `<svg class="gg-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Execution flow of recent stories">` +
        `<path class="fl-main" d="M${x0} 0 L${x0} ${H}"/>${edges}${stubs}${dots}</svg>` };
    }

    // ---- flow: story filter (a button that opens a panel of checkboxes, grouped by feature, with search) ----
    const idNum = id => parseInt(String(id).replace(/\D/g, ''), 10) || 0;
    const flowFeat = sid => (FLOW.features || []).find(x => x.id === (FLOW.stories[sid] || {}).feature) || null;
    const flowPhase = sid => { const f = flowFeat(sid); return f && (FLOW.phases || []).find(x => x.id === f.phase) || null; };
    const flowFeatName = sid => { const f = (FLOW.features || []).find(x => x.id === (FLOW.stories[sid] || {}).feature); return f ? f.name : ''; };
    function flowGroups(){
      const q = flowQuery.trim().toLowerCase(), groups = [], byId = {};
      (FLOW.features || []).concat([{ id:'', name:'Other' }]).forEach(f => { const g = { id:f.id, name:f.name, ids:[] }; byId[f.id] = g; groups.push(g); });
      Object.keys(FLOW.stories || {}).sort((a, b) => idNum(b) - idNum(a)).forEach(sid => {
        const s = FLOW.stories[sid], g = byId[s.feature] || byId[''];
        if(!q || (sid + ' ' + (s.name || '') + ' ' + g.name).toLowerCase().includes(q)) g.ids.push(sid);
      });
      return groups.filter(g => g.ids.length);
    }
    function renderFlowGroups(){
      const el = root.querySelector('#flGroups');
      if(!el) return;
      const groups = flowGroups();
      el.innerHTML = groups.length ? groups.map(g => `<div class="fl-group"><div class="fl-group-h">
        <label><input type="checkbox" data-fgrp="${esc(g.id)}"> ${g.id ? RM.idChip('Feature', g.id) + ' ' : ''}<span>${esc(g.name)}</span></label>
        <span class="mono fl-group-n">${g.ids.filter(i => flowSel.has(i)).length}/${g.ids.length}</span></div>
        ${g.ids.map(i => `<label class="fl-opt"><input type="checkbox" data-fchk="${esc(i)}"${flowSel.has(i) ? ' checked' : ''}>
          <b class="mono">${esc(i)}</b> <span>${esc(FLOW.stories[i].name || '')}</span></label>`).join('')}</div>`).join('')
        : `<div class="empty-note">No stories match.</div>`;
      groups.forEach(g => {
        const box = [...el.querySelectorAll('[data-fgrp]')].find(b => b.dataset.fgrp === g.id);
        const on = g.ids.filter(i => flowSel.has(i)).length;
        if(box){ box.checked = on === g.ids.length; box.indeterminate = on > 0 && on < g.ids.length; }
      });
    }
    function updateFlowButton(){
      const b = root.querySelector('#flFilterBtn');
      if(!b) return;
      const total = Object.keys(FLOW.stories || {}).length;
      b.textContent = flowSel.size ? `Stories: ${flowSel.size} of ${total} selected ▾` : `Stories: all ${total} ▾`;
      b.setAttribute('aria-expanded', flowPanelOpen);
      b.classList.toggle('is-on', flowSel.size > 0);
      const a = root.querySelector('#flShowAll');
      if(a) a.hidden = flowSel.size === 0;
    }
    function setFlowPanel(open, focus){
      flowPanelOpen = open;
      const p = root.querySelector('#flPanel');
      if(p) p.hidden = !open;
      updateFlowButton();
      if(focus === 'search'){ const s = root.querySelector('#flSearch'); if(s) s.focus(); }
      else if(focus === 'btn'){ const b = root.querySelector('#flFilterBtn'); if(b) b.focus(); }
    }
    function applyFlowFilter(){
      if(flowOne && flowSel.size && !flowSel.has(flowOne)) flowOne = null;
      updateFlowButton(); renderFlowGroups(); renderFlowBody();
    }

    // full details of one story in the flow: the same pane the Plan board uses (archived stories load plan-archive.json lazily)
    function flowDetail(id){
      const s = stories.find(x => x.id === id) || (ARCH && ARCH.stories.find(x => x.id === id));
      if(s) return RM.story.detailPanel(env, s, { archive:!!s.archived, noHide:true });
      if(!ARCH && !archError){ loadArchive(); return `<div class="empty-note">Loading story details...</div>`; }
      return `<div class="empty-note">${esc(id)} is not in the plan data. <button class="toolbar-btn" data-close>✕ Close</button></div>`;
    }

    function renderFlowBody(scrollTop){
      const body = root.querySelector('#flBody');
      if(!body) return;
      const prev = body.querySelector('.fl-scroll');
      const keep = scrollTop != null ? scrollTop : (prev ? prev.scrollTop : 0);
      const all = FLOW.rows || [], rows = flowSel.size ? all.filter(r => flowSel.has(r.story)) : all;
      const g = flowGraph(rows), one = flowOne;
      const items = rows.map(r => {
        const st = FLOW.stories[r.story] || {}, meta = statusMeta[r.state] || statusMeta['not-started'];
        const role = (ROLE[r.state] || r.state) + (r.loop ? ` ↻${r.loop}` : '');
        const fn = flowFeatName(r.story), ph = flowPhase(r.story), phn = ph ? ph.name : '';
        const tokTxt = r.tok ? `${r.tok.toLocaleString('en-US')} tokens` : '';
        const title = `${r.ts.replace('T', ' ')} UTC · ${r.story} ${st.name || ''} · ${role}${r.agent ? ' · ' + r.agent : ''}${tokTxt ? ' · ' + tokTxt : ''}${fn ? ' · ' + fn : ''}${phn ? ' · ' + phn : ''}`;
        const isDone = r.state === 'done';
        const ASRC = { event:'recorded on the status event', run:'from the matched subagent run', story:"from the story record (its latest agent or critic)" };
        const agentTip = r.agent ? `${r.chg ? r.agent + ' (a different agent than earlier in this stage)' : r.agent} · source: ${ASRC[r.asrc] || r.asrc || 'unknown'}`
          : (isDone ? 'closing the story has no agent' : 'not recorded: no status event, subagent run or story record names an agent for this step');
        const unat = !r.tok && !isDone && st.unattr;
        const tokCell = r.tok ? flowTok(r.tok) : (unat ? 'unattributed' : '-');
        const tokTip = r.tok ? tokTxt : (unat ? st.unattr : (isDone ? 'closing the story has no tokens' : 'no subagent run recorded for this step'));
        return `<li class="gg-row fl-row${one === r.story ? ' fl-row-sel' : ''}" data-fsid="${esc(r.story)}" tabindex="0" role="button" aria-label="Open details: ${esc(r.story + ' ' + (st.name || ''))}" title="${esc(title)}">
        <span class="fl-c-phase fl-cell" title="${esc(phn)}">${esc(ph ? ph.short : '')}</span>
        <span class="fl-c-feat fl-cell" title="${esc(fn)}">${esc(fn)}</span>
        <span class="fl-c-story gg-subject"><b class="mono">${esc(r.story)}</b> ${esc(st.name || '')}</span>
        <span class="fl-c-step fl-role mono${r.loop ? ' fl-role-loop' : ''}" style="--rc:${meta.color}">${esc(role)}</span>
        <span class="fl-c-agent fl-cell fl-agent mono${r.agent ? '' : ' fl-none'}${r.chg ? ' fl-chg' : ''}" title="${esc(agentTip)}">${esc(r.agent || (isDone ? '-' : 'not recorded'))}</span>
        <span class="fl-c-tok fl-cell mono${r.tok ? '' : ' fl-none'}${unat ? ' fl-unattr' : ''}" title="${esc(tokTip)}">${esc(tokCell)}</span>
        <span class="fl-c-date fl-cell gg-date mono">${esc(flowStamp(r.ts))}</span></li>`;
      }).join('');
      const head = `<div class="fl-head"><span class="fl-hg" style="width:${g.W}px">Flow</span><div class="fl-hcols">${
        FLOW_COLS.map(([k, label]) => `<span class="fl-c-${k}">${esc(label)}</span>`).join('')}</div></div>`;
      const nStories = new Set(rows.map(r => r.story)).size;
      body.innerHTML = `${one ? `<div class="list-detail fl-pane">${flowDetail(one)}</div>` : ''}
      <div class="fl-scroll"><div class="fl-inner">${head}<div class="gg-body" style="--gg-h:${g.H}px"><div class="gg-graph" style="width:${g.W}px">${g.svg}</div><ol class="gg-rows">${items}</ol></div></div></div>
      <p class="tok-note">${flowSel.size ? `Showing ${nStories} selected ${nStories === 1 ? 'story' : 'stories'} (${rows.length} steps). ` : ''}Last ${esc(FLOW.days)} days, newest ${esc(all.length)} steps (cap ${esc(FLOW.max_events)}). Older activity is not loaded. Tokens are the fresh tokens (input, cache write, output) of the subagent runs on that step; a dash means no run was recorded for it; “unattributed” means the story has spend that matched no step (hover for why). An agent reads “not recorded” when no event, run or story record names one (hover an agent for its source). Read from the local ledger; no tokens are used.</p>`;
      const sc = body.querySelector('.fl-scroll');
      if(sc) sc.scrollTop = keep;
    }

    function renderFlow(){
      if(!FLOW){
        mainEl.innerHTML = flowError
          ? `<div class="error-box"><b>flow.json</b> failed to load. ${esc(flowError)} Run <span class="mono">roadmap.py refresh</span> and publish again.</div>`
          : `<div class="empty-note">Loading execution flow...</div>`;
        return;
      }
      const rows = FLOW.rows || [];
      if(!rows.length){ mainEl.innerHTML = `<div class="empty-note">No story activity recorded in the last ${esc(FLOW.days || 14)} days.</div>`; return; }
      const prev = mainEl.querySelector('.fl-scroll'), keep = prev ? prev.scrollTop : 0;
      mainEl.innerHTML = `<div class="fl-note">Newest at the top. The main line runs down the left. Each story branches off it, moves through its agents
        (planner, plan critic, implementer, review critic), and merges back (hollow dot) when it closes. The shape of a point is the stage entered. A stage that
        comes round again is a loop: dashed line and ↻2, ↻3. An accent line with a ring is a story still open. Columns: phase, feature, story, step, agent
        (bold when it differs from the stage's earlier agent), tokens and date-time (your local time). Click a story for its full details and to show only that story.</div>
      <div class="fl-legend" aria-label="Shape key: stage entered">${shapeKey}</div>
      <div class="fl-bar"><div class="fl-filter">
        <button class="toolbar-btn fl-fbtn" id="flFilterBtn" data-fact="toggle" aria-haspopup="true" aria-controls="flPanel" aria-expanded="false"></button>
        <div class="fl-panel" id="flPanel" role="group" aria-label="Choose stories to show" hidden>
          <input id="flSearch" type="search" placeholder="Search stories or features" aria-label="Search stories" value="${esc(flowQuery)}">
          <div class="fl-panel-tools"><button class="toolbar-btn" data-fact="all">Select all</button><button class="toolbar-btn" data-fact="clear">Clear</button>
            <button class="toolbar-btn" data-fact="done">Close</button></div>
          <div class="fl-groups" id="flGroups"></div>
        </div></div><button class="toolbar-btn fl-showall" id="flShowAll" data-fact="showall" hidden>Show all stories</button></div>
      <div id="flBody"></div>`;
      renderFlowGroups();
      renderFlowBody(keep);
      setFlowPanel(flowPanelOpen);
    }

    // the details pane's Close button; the pane has no hide controls here (noHide)
    function closeStory(){
      const id = flowOne; flowOne = null; renderFlowBody();
      const row = id && [...mainEl.querySelectorAll('.fl-row')].find(x => x.dataset.fsid === id);
      if(row) row.focus();
    }
    // clicking a story opens its details AND narrows the flow to that story (its whole workflow, lanes re-packed);
    // the filter button and panel follow (1 of N selected), "Show all stories" undoes it
    function openFlowStory(id){
      flowSel.clear(); flowSel.add(id); flowOne = id;
      updateFlowButton(); renderFlowGroups(); renderFlowBody(0);
      const el = mainEl.querySelector('.fl-pane');
      if(el) el.scrollIntoView({ block:'nearest' });
    }

    // ---- events ----
    mainEl.addEventListener('click', e => {
      const fa = e.target.closest('[data-fact]');
      if(fa){
        const act = fa.dataset.fact;
        if(act === 'toggle') return setFlowPanel(!flowPanelOpen, flowPanelOpen ? 'btn' : 'search');
        if(act === 'done') return setFlowPanel(false, 'btn');
        if(act === 'showall'){ flowSel.clear(); flowOne = null; updateFlowButton(); renderFlowGroups(); renderFlowBody(0); return setFlowPanel(false, 'btn'); }
        if(act === 'all') flowGroups().forEach(g => g.ids.forEach(i => flowSel.add(i)));
        else flowSel.clear();
        return applyFlowFilter();
      }
      if(e.target.closest('[data-close]')) return closeStory();
      const fr = e.target.closest('[data-fsid]');
      if(fr) return openFlowStory(fr.dataset.fsid);
    });
    mainEl.addEventListener('change', e => {
      const one = e.target.closest && e.target.closest('[data-fchk]'), grp = e.target.closest && e.target.closest('[data-fgrp]');
      if(one){ e.target.checked ? flowSel.add(one.dataset.fchk) : flowSel.delete(one.dataset.fchk); applyFlowFilter(); }
      else if(grp){
        const g = flowGroups().find(x => x.id === grp.dataset.fgrp);
        if(g) g.ids.forEach(i => e.target.checked ? flowSel.add(i) : flowSel.delete(i));
        applyFlowFilter();
      }
    });
    mainEl.addEventListener('input', e => { if(e.target.id === 'flSearch'){ flowQuery = e.target.value; renderFlowGroups(); } });
    mainEl.addEventListener('keydown', e => {
      const fr = e.target.closest && e.target.closest('.fl-row[data-fsid]');
      if(fr && e.target === fr && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); return openFlowStory(fr.dataset.fsid); }
    });
    // page-level keys act only while this tab is showing; a re-mount (Reload) replaces the earlier handlers
    const panel = root.closest ? root.closest('.tab-panel') : null;
    const showing = () => root.isConnected && !(panel && panel.hidden);
    if(RM.flowDocHandlers){
      document.removeEventListener('keydown', RM.flowDocHandlers.key);
      document.removeEventListener('click', RM.flowDocHandlers.click);
    }
    RM.flowDocHandlers = {
      key: e => {
        if(e.key !== 'Escape' || !showing()) return;
        if(flowPanelOpen) setFlowPanel(false, 'btn');
        else if(flowOne) closeStory();
      },
      click: e => {
        if(showing() && flowPanelOpen && !(e.target.closest && e.target.closest('.fl-filter'))) setFlowPanel(false);
      }
    };
    document.addEventListener('keydown', RM.flowDocHandlers.key);
    document.addEventListener('click', RM.flowDocHandlers.click);

    loadFlow();
    renderFlow();
  } };
})();
