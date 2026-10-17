/* Plan tab: ring, phase stepper, Plan/Archive sub-tabs, list view, hide-completed control. (Execution flow is its own tab, tab-flow.js.) */
(function () {
  'use strict';
  const RM = window.RM;
  const esc = RM.esc, fmtNum = RM.fmtNum, fmtTok = RM.fmtTok;

  RM.tabs.plan = { mount(root, data, ctx) {
    const PLAN = data.plan || {};
    const TOK = data.tokens || {};
    const phases = PLAN.phases || [], features = PLAN.features || [], stories = PLAN.stories || [];
    const agents = PLAN.agents || {};
    const counts = PLAN.counts || { overall: { done: 0, total: 0 }, archivedPhases: 0, phases: {} };
    let ARCH = null, archLoading = false, archError = '';

    root.innerHTML = `
  <div class="plan-top">
    <div class="ring-wrap">
      <div class="ring" id="ring"><div class="hole"><b class="mono" id="pct-text">0%</b><span>complete</span></div></div>
      <div class="ring-label"><strong id="doneFrac"></strong><span id="activeSummary"></span></div>
    </div>
  </div>
  <button class="reset-pill" id="resetPill">✕ clear filter</button>
  <div class="roadmap" id="roadmap"></div>
  <div class="layout"><div>
    <div class="tabs" role="tablist">
      <button id="tabPlan" role="tab" aria-selected="true">Plan</button>
      <button id="tabArchive" role="tab" aria-selected="false">Archive <span class="tab-count mono" id="archCount">0</span></button>
    </div>
    <div class="archive-tools" id="archiveTools" hidden>
      <input id="archiveSearch" type="search" placeholder="Search archived phases, features, stories, agents" aria-label="Search archive">
    </div>
    <div class="toolbar-row" id="planToolbar">
      <div class="tools-right">
        <div class="features-toolbar" id="doneTools" hidden>
          <label class="done-slider" title="Hide completed stories oldest first. A feature hides with its last story. Unfinished work stays visible.">
            <input type="range" id="doneSlider" min="0" max="0" step="1" value="0" aria-label="Hide completed stories, oldest first">
            <span class="done-slider-label mono" id="doneSliderLabel">Showing all completed</span>
          </label>
        </div>
        <div class="features-toolbar" id="hiddenTools" hidden>
          <button class="toolbar-btn" id="toggleHidden">Show hidden</button>
          <button class="toolbar-btn" id="unhideAll">Unhide all</button>
        </div>
        <div class="features-toolbar" id="hiddenFeatureTools" hidden>
          <button class="toolbar-btn" id="toggleHiddenFeatures">Show hidden features</button>
          <button class="toolbar-btn" id="unhideAllFeatures">Unhide all features</button>
        </div>
        <div class="features-toolbar" id="listTools" hidden>
          <button class="toolbar-btn" id="expandAll">Expand all</button>
          <button class="toolbar-btn" id="collapseAll">Collapse all</button>
          <button class="toolbar-btn" id="expandCompleted" title="Expand every feature that has a completed story currently shown (respects the completed slider and hidden filters), whether or not the feature is fully done.">Expand completed</button>
          <button class="toolbar-btn" id="expandActive" title="Expand every in-progress feature that is currently shown.">Expand in progress</button>
        </div>
      </div>
    </div>
    <div id="phaseSections"></div>
  </div></div>`;

    const $ = id => root.querySelector('#' + id);
    const mainEl = $('phaseSections');

    // shared with the Execution flow tab: RM.story lives in app.js
    const statusMeta = RM.story.statusMeta;
    // any status other than not-started and done means the story is in flight
    const isActiveStatus = s => s.status !== 'done' && s.status !== 'not-started';
    const modelColor = RM.story.modelColor;

    const allFeatures = () => features.concat(ARCH ? ARCH.features : []);
    const allPhases = () => phases.concat(ARCH ? ARCH.phases : []);
    const allStories = () => stories.concat(ARCH ? ARCH.stories : []);
    const featureOf = id => allFeatures().find(f => f.id === id) || { id, name:id, phase:'' };
    const phaseOf = id => allPhases().find(p => p.id === id) || { id, name:id };
    const storiesForFeature = fid => stories.filter(s => s.feature === fid);
    const featuresForPhase = pid => features.filter(f => f.phase === pid);
    const storiesForPhase = pid => stories.filter(s => (features.find(f => f.id === s.feature) || {}).phase === pid);
    const ALL_DONE_NOTE = 'All phases are complete. See the Archive tab.';
    const parseDate = iso => { const d = new Date(iso + 'T00:00:00'); return isNaN(d) ? null : d; };
    const fmtDate = iso => { const d = iso && parseDate(iso); return d ? d.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : (iso || ''); };
    const monthLabel = iso => { const d = iso && parseDate(iso); return d ? d.toLocaleDateString('en-US', { month:'long', year:'numeric' }) : 'Undated'; };

    function progressOf(list){
      const done = list.filter(s => s.status === 'done').length;
      const total = list.length;
      return { done, total, pct: total ? Math.round((done/total)*100) : 0 };
    }
    function aggStatus(list){
      const p = progressOf(list);
      if(p.pct === 100 && p.total > 0) return 'done';
      if(p.done > 0 || list.some(isActiveStatus)) return 'active';
      return 'queued';
    }
    // phase progress comes from PLAN.counts (it includes the archived stories of the phase)
    function phaseProgress(pid){
      const c = (counts.phases || {})[pid] || { done:0, total:0 };
      return { done:c.done, total:c.total, pct: c.total ? Math.round((c.done/c.total)*100) : 0 };
    }
    function phaseAgg(pid){
      const p = phaseProgress(pid);
      if(p.pct === 100 && p.total > 0) return 'done';
      if(p.done > 0 || storiesForPhase(pid).some(isActiveStatus)) return 'active';
      return 'queued';
    }
    const aggColor = agg => ({ done:statusMeta.done, active:statusMeta.progress, queued:statusMeta['not-started'] }[agg].color);

    // ---- state ----
    let tab = 'plan', activeFilter = null, selected = null, showHidden = false, archiveQuery = '';
    const expanded = new Set(features.filter(f => storiesForFeature(f.id).some(isActiveStatus)).map(f => f.id));
    // fully done features are minimized by default; doneOpen holds the ones the reader expanded (per session)
    const doneOpen = new Set();
    const isDoneFeature = f => { const l = storiesForFeature(f.id); return l.length > 0 && l.every(s => s.status === 'done'); };
    const doneFeatures = () => features.filter(isDoneFeature);
    const featTokens = f => ((TOK.features || {})[f.id] || {}).fresh || 0;
    const featTok = f => { const n = featTokens(f); return n ? `${fmtTok(n)} tok` : 'no tokens'; };
    const featOpen = f => isDoneFeature(f) ? doneOpen.has(f.id) : expanded.has(f.id);
    const archOpen = new Set();

    // One-time carry-over of a viewer's saved choice from the old project-prefixed key to the neutral key.
    const migrateStore = (nk, ok) => { if (RM.store(nk) == null) { const v = RM.store(ok); if (v != null) RM.store(nk, v); } return nk; };
    const HIDE_KEY = migrateStore('roadmap-hidden-v3', 'ttpy-roadmap-hidden-v3');
    const hiddenIds = new Set(RM.store(HIDE_KEY) || []);
    const saveHidden = () => RM.store(HIDE_KEY, [...hiddenIds]);
    const isHidden = s => s.status === 'done' && hiddenIds.has(s.id);
    const isShown = s => showHidden || !isHidden(s);

    const HIDE_FEATURE_KEY = migrateStore('roadmap-hidden-features-v2', 'ttpy-roadmap-hidden-features-v2');
    const hiddenFeatureIds = new Set(RM.store(HIDE_FEATURE_KEY) || []);
    const saveHiddenFeatures = () => RM.store(HIDE_FEATURE_KEY, [...hiddenFeatureIds]);
    const isFeatureHidden = f => isDoneFeature(f) && hiddenFeatureIds.has(f.id);
    let showHiddenFeatures = false;

    // A slider hides completed stories oldest first (unfinished work is never hidden). Position = how many completed
    // stories are hidden (0 = show all, max = hide all). A feature has no slider step of its own: it hides exactly when
    // all of its stories are hidden (by the slider or by a manual Hide), so a feature never shows without a story.
    // Remembered per viewer; RM.store swallows storage errors, so the page works without localStorage.
    // v2: the old v1 position counted stories plus features, so it is ignored.
    const HIDE_DONE_COUNT_KEY = migrateStore('roadmap-hide-completed-count-v2', 'ttpy-roadmap-hide-completed-count-v2');
    const savedHideDoneCount = Number(RM.store(HIDE_DONE_COUNT_KEY));
    let hideDoneCount = Number.isInteger(savedHideDoneCount) && savedHideDoneCount > 0 ? savedHideDoneCount : 0;
    // completed stories, oldest first; a story with no date sorts as oldest
    function completedStoriesOldestFirst(){
      return stories.filter(s => s.status === 'done').map(s => ({ id:s.id, date:s.completed || '' }))
        .sort((a, b) => a.date.localeCompare(b.date));
    }
    let cutoffHiddenIds = new Set();
    let cutoffHiddenCount = 0, cutoffTotalCount = 0, cutoffDate = '';
    // recomputed on every render so the slider stays valid when the plan data changes
    function updateCutoff(){
      const items = completedStoriesOldestFirst();
      cutoffTotalCount = items.length;
      cutoffHiddenCount = Math.min(hideDoneCount, items.length);
      const hidden = items.slice(0, cutoffHiddenCount);
      cutoffHiddenIds = new Set(hidden.map(i => i.id));
      cutoffDate = hidden.length ? hidden[hidden.length - 1].date : '';
    }
    function doneSliderLabel(){
      if(cutoffHiddenCount === 0) return 'Showing all completed';
      if(cutoffHiddenCount === cutoffTotalCount) return 'Hiding all completed';
      return `Hiding ${cutoffHiddenCount} of ${cutoffTotalCount} completed stories` + (cutoffDate ? ` (up to ${cutoffDate})` : ' (undated)');
    }
    const isCutoffHiddenStory = s => cutoffHiddenIds.has(s.id);
    const shownStory = s => isShown(s) && !isCutoffHiddenStory(s);
    // a feature with stories but none showing (slider and manual Hide combined) is hidden with them
    const hasNoShownStory = f => { const l = storiesForFeature(f.id); return l.length > 0 && !l.some(shownStory); };
    // features on screen right now that hold at least one shown completed story: inside the active phase
    // filter, not feature-hidden, and with a completed story the slider and manual Hide leave showing.
    // A feature need not be fully done (the slider counts completed stories in in-progress features too).
    function visibleCompletedFeatures(){
      const visiblePhases = activeFilter ? phases.filter(p => p.id === activeFilter) : phases;
      const phaseIds = new Set(visiblePhases.map(p => p.id));
      return features.filter(f => phaseIds.has(f.phase) && (showHiddenFeatures || !isFeatureHidden(f))
        && storiesForFeature(f.id).some(s => s.status === 'done' && shownStory(s)));
    }
    // in-progress features are never individually hidden or slider-cut (only done stories/features
    // can be), so the only filter that applies is the active phase one
    function visibleActiveFeatures(){
      const visiblePhases = activeFilter ? phases.filter(p => p.id === activeFilter) : phases;
      const phaseIds = new Set(visiblePhases.map(p => p.id));
      return features.filter(f => phaseIds.has(f.phase) && aggStatus(storiesForFeature(f.id)) === 'active');
    }

    // ---- shared pieces ----
    const agentChip = id => RM.story.agentChip(agents, id);
    const usageOf = id => (TOK.stories || {})[id] || null;
    const phaseTokens = pid => ((TOK.phases || {})[pid] || {}).fresh || 0;
    const phaseTok = pid => { const n = phaseTokens(pid); return n ? `${fmtTok(n)} tok` : 'no tokens logged'; };
    const PHASE_TOK_TIP = 'Fresh tokens used across this phase (new input + cache writes + output), summed from its stories';
    function tokChip(s){
      const u = usageOf(s.id);
      return u ? `<span class="tok-chip mono" title="${fmtNum(u.fresh)} fresh tokens on this story (new input + cache writes + output)">${fmtTok(u.fresh)} tok</span>` : '';
    }
    function hideBtn(s){
      if(s.status !== 'done') return '';
      return isHidden(s)
        ? `<span class="mc-actions"><button class="hide-btn" data-unhide="${esc(s.id)}">Unhide</button></span>`
        : `<span class="mc-actions"><button class="hide-btn" data-hide="${esc(s.id)}">Hide</button></span>`;
    }
    function predictedChip(f){
      const parts = [];
      if(f.points != null) parts.push(`${f.points} pts`);
      if(f.estTokens != null) parts.push(`${fmtTok(f.estTokens)} tok est`);
      return parts.join(' · ');
    }
    function hideFeatureBtn(f){
      if(!isDoneFeature(f)) return '';
      return isFeatureHidden(f)
        ? `<span class="mc-actions"><button class="hide-btn" data-unhidefeat="${esc(f.id)}">Unhide</button></span>`
        : `<span class="mc-actions"><button class="hide-btn" data-hidefeat="${esc(f.id)}">Hide</button></span>`;
    }
    const statusChip = RM.story.statusChip;

    const escChip = RM.story.escChip;

    const detailPanel = (s, opts = {}) => RM.story.detailPanel({ agents, tokens:TOK, featureOf, phaseOf, isHidden }, s, opts);

    // ---- header + phase stepper ----
    function renderHeader(){
      const o = counts.overall || { done:0, total:0 };
      const pct = o.total ? Math.round((o.done/o.total)*100) : 0;
      $('ring').style.setProperty('--pct', pct);
      $('pct-text').textContent = pct + '%';
      $('doneFrac').textContent = `${o.done} of ${o.total} stories done`;
      const active = stories.filter(isActiveStatus).length;
      const queued = stories.filter(s => s.status === 'not-started').length;
      $('activeSummary').textContent = `${active} active, ${queued} queued across ${features.length} features`;
    }

    function renderRoadmap(){
      const el = $('roadmap');
      el.innerHTML = phases.map((ph, i) => {
        const p = phaseProgress(ph.id);
        const agg = phaseAgg(ph.id);
        const label = agg === 'done' ? 'Done' : agg === 'active' ? 'Active' : 'Queued';
        return `<button class="step ${activeFilter===ph.id?'active':''}" data-agg="${agg}" data-id="${esc(ph.id)}">
        <span class="num mono">${String(i+1).padStart(2,'0')}</span>
        <span class="step-name">${esc(ph.name)} ${RM.idChip('Phase', ph.id)}</span>
        <span class="bar"><i style="width:${p.pct}%"></i></span>
        <span class="step-meta mono">${p.done}/${p.total} · ${label}</span>
        <span class="step-tok mono" title="${PHASE_TOK_TIP}">${phaseTok(ph.id)}</span>
      </button>`;
      }).join('');
      el.querySelectorAll('.step').forEach(btn => btn.addEventListener('click', () => {
        activeFilter = activeFilter === btn.dataset.id ? null : btn.dataset.id;
        selected = null;
        renderRoadmap(); renderMain();
        $('resetPill').classList.toggle('show', !!activeFilter);
      }));
    }

    // ---- plan: list view ----
    function storyRow(s, opts = {}){
      const meta = statusMeta[s.status] || statusMeta.done;
      return `<div class="story-row${isHidden(s) ? ' is-hidden' : ''}" data-sid="${esc(s.id)}" tabindex="0" role="button" aria-label="Open details: ${esc(s.id + ' ' + s.name)}">
      <span class="s-dot" style="background:${meta.color}"></span>
      <span class="s-status-label">${meta.label}</span>
      <span class="s-title">${RM.idChip('Story', s.id)} ${esc(s.name)}</span>
      <span class="s-right">
        ${tokChip(s)}
        ${agentChip(s.agent)}
        ${s.critic ? `<span class="unassigned" style="font-style:normal;">·&nbsp;reviewed by</span>${agentChip(s.critic)}` : ''}
        ${s.loop ? `<span class="loop-chip">↻ loop ${esc(s.loop)}</span>` : ''}
        ${escChip(s)}
        ${opts.archive ? (s.completed ? `<span class="unassigned" style="font-style:normal;">${esc(fmtDate(s.completed))}</span>` : '') : hideBtn(s)}
      </span>
    </div>${selected === s.id ? `<div class="list-detail">${detailPanel(s, opts)}</div>` : ''}`;
    }

    function featureCard(f){
      const list = storiesForFeature(f.id);
      const p = progressOf(list);
      const agg = aggStatus(list);
      const label = { done:'Done', active:'In progress', queued:'Not started' }[agg];
      const isOpen = featOpen(f);
      const isDone = isDoneFeature(f);
      const tok = featTokens(f);
      const pred = predictedChip(f);
      return `<div class="feature-card ${isOpen?'open':''}${isDone ? ' is-done' : ''}${isFeatureHidden(f) ? ' is-hidden' : ''}" data-fid="${esc(f.id)}">
      <button class="feature-head" ${isDone ? 'data-donetoggle' : 'data-toggle'}="${esc(f.id)}" aria-expanded="${isOpen}">
        <span class="chev">▶</span>
        <span class="f-info">
          <span class="f-name">${RM.idChip('Feature', f.id)} ${esc(f.name)}</span>
          <span class="f-bar"><i style="width:${p.pct}%; background:${aggColor(agg)}"></i></span>
        </span>
        <span class="f-frac mono">${p.done}/${p.total}</span>
        ${pred ? `<span class="f-frac mono">${pred}</span>` : ''}
        ${tok ? `<span class="f-frac mono">${featTok(f)}</span>` : ''}
        ${statusChip(aggColor(agg), label)}
        ${hideFeatureBtn(f)}
      </button>
      ${isOpen ? `<div class="story-list">${list.filter(shownStory).map(s => storyRow(s)).join('')}</div>` : ''}
    </div>`;
    }

    function renderFeatures(){
      const visiblePhases = activeFilter ? phases.filter(p => p.id === activeFilter) : phases;
      if(!visiblePhases.length){ mainEl.innerHTML = `<div class="empty-note">${ALL_DONE_NOTE}</div>`; return; }
      mainEl.innerHTML = visiblePhases.map(ph => {
        const p = phaseProgress(ph.id);
        const fl = featuresForPhase(ph.id);
        const visible = fl.filter(f => !hasNoShownStory(f) && (showHiddenFeatures || !isFeatureHidden(f)));
        return `<div class="phase-section">
        <div class="phase-section-head">
          <h2>${RM.idChip('Phase', ph.id)} ${esc(ph.name)}</h2>
          <span class="frac mono" title="${PHASE_TOK_TIP}">${p.done}/${p.total} stories · ${phaseTok(ph.id)} · ${fl.length} ${fl.length === 1 ? 'feature' : 'features'}</span>
        </div>
        <div class="feature-list">${visible.length ? visible.map(featureCard).join('') : `<div class="empty-note">${fl.length ? (cutoffHiddenCount > 0 ? 'All features here are complete and hidden.' : 'All features hidden.') : 'No features yet.'}</div>`}</div>
      </div>`;
      }).join('');
    }

    // ---- archive ----
    const agentIdsOf = list => [...new Set(list.flatMap(s => [s.agent, s.critic]).filter(Boolean))];
    const agentName = i => (agents[i] || { name:i }).name;
    function archiveEntries(){
      const q = archiveQuery.trim().toLowerCase();
      const nestedEntry = f => { const list = ARCH.stories.filter(s => s.feature === f.id); return { f, list, ids:agentIdsOf(list), date:f.completed || '' }; };
      const text = e => [e.ph.name, ...e.feats.map(x => x.f.name), ...e.list.map(s => s.name), ...e.ids.map(agentName)];
      return ARCH.phases.map(ph => {
        const feats = ARCH.features.filter(f => f.phase === ph.id).map(nestedEntry);
        const list = feats.flatMap(x => x.list);
        return { id:ph.id, ph, list, feats, ids:agentIdsOf(list), date:ph.completed || '' };
      }).filter(e => !q || text(e).join(' ').toLowerCase().includes(q))
        .sort((a, b) => (b.date || '').localeCompare(a.date || '') || a.ph.name.localeCompare(b.ph.name));
    }

    // One avatar per distinct model tier (max 3: a/b/c), not per agent -- a feature with many
    // stories can have many differently-named implementers of the SAME model, and listing every
    // one overflows/overlaps at narrow widths. Count badge + full names in the tooltip keep the
    // detail; per-story rows (agentChip) still show each individual agent when expanded.
    const avatarsFor = ids => {
      const list = ids.map(i => agents[i] || { name:i, initials:'?', model:'a', modelLabel:'' });
      const byModel = new Map();
      list.forEach(a => { if(!byModel.has(a.model)) byModel.set(a.model, []); byModel.get(a.model).push(a); });
      return [...byModel.entries()].map(([model, group]) => {
        const label = group.length > 1 ? String(group.length) : esc(group[0].initials);
        const title = group.map(a => `${a.name} · ${a.modelLabel}`).join(', ');
        return `<span class="avatar" title="${esc(title)}" style="background:${modelColor(model)}">${label}</span>`;
      }).join('');
    };

    function nestedFeatureCard(e){
      const open = archOpen.has(e.f.id);
      const count = `${e.list.length} ${e.list.length === 1 ? 'story' : 'stories'}`;
      const tok = featTok(e.f);
      return `<div class="feature-card arch-card ${open ? 'open' : ''}">
      <button class="feature-head" data-arch-toggle="${esc(e.f.id)}" aria-expanded="${open}">
        <span class="chev">▶</span>
        <span class="f-info">
          <span class="f-name">${RM.idChip('Feature', e.f.id)} ${esc(e.f.name)}</span>
          <span class="arch-sub mono">${count} · ${tok}</span>
        </span>
        <span class="arch-agents">${avatarsFor(e.ids)}</span>
        <span class="f-frac mono">${e.date ? esc(fmtDate(e.date)) : 'Undated'}</span>
      </button>
      ${open ? `<div class="story-list">${e.list.map(s => storyRow(s, { archive:true })).join('')}</div>` : ''}
    </div>`;
    }

    function phaseArchiveCard(e){
      const open = archOpen.has(e.ph.id);
      const fc = e.feats.length;
      return `<div class="feature-card arch-card ${open ? 'open' : ''}">
      <button class="feature-head" data-arch-toggle="${esc(e.ph.id)}" aria-expanded="${open}">
        <span class="chev">▶</span>
        <span class="f-info">
          <span class="f-name">${RM.idChip('Phase', e.ph.id)} ${esc(e.ph.name)}</span>
          <span class="arch-sub mono">Phase · ${fc} ${fc === 1 ? 'feature' : 'features'} · ${e.list.length} ${e.list.length === 1 ? 'story' : 'stories'}${phaseTokens(e.ph.id) ? ` · ${phaseTok(e.ph.id)}` : ''}</span>
        </span>
        <span class="arch-agents">${avatarsFor(e.ids)}</span>
        <span class="f-frac mono">${e.date ? esc(fmtDate(e.date)) : 'Undated'}</span>
      </button>
      ${open ? `<div class="story-list arch-nested">${e.feats.map(nestedFeatureCard).join('')}</div>` : ''}
    </div>`;
    }

    function archiveSection(list, emptyText){
      let html = '', last = null;
      list.forEach(e => {
        const m = monthLabel(e.date);
        if(m !== last){ html += `<h3 class="arch-month">${esc(m)}</h3>`; last = m; }
        html += phaseArchiveCard(e);
      });
      return `<div class="phase-section">
      <div class="phase-section-head"><h2>Archived phases</h2><span class="frac mono">${list.length}</span></div>
      ${list.length ? html : `<div class="empty-note">${emptyText}</div>`}
    </div>`;
    }

    function renderArchive(){
      if(!ARCH){
        mainEl.innerHTML = archError
          ? `<div class="error-box"><b>plan-archive.json</b> failed to load. ${esc(archError)} Run <span class="mono">roadmap.py refresh</span> and publish again.</div>`
          : `<div class="empty-note">Loading archive...</div>`;
        return;
      }
      if(!ARCH.phases.length){
        mainEl.innerHTML = `<div class="empty-note">No archived phases yet. A phase moves here when every story in it is done.</div>`;
        return;
      }
      mainEl.innerHTML = archiveSection(archiveEntries(), 'No archived phases match.');
    }

    function loadArchive(){
      if(ARCH || archLoading) return;
      archLoading = true; archError = '';
      ctx.load('archive').then(a => {
        ARCH = { phases:a.phases || [], features:a.features || [],
          stories:(a.stories || []).map(s => Object.assign({ status:'done', archived:true }, s)) };
      }).catch(e => { archError = String(e && e.message || e) + '.'; })
        .then(() => {
          archLoading = false;
          if(tab === 'archive') renderMain();
        });
    }

    // ---- main pane ----
    function renderMain(){
      $('archCount').textContent = (counts.archivedPhases || 0);
      $('tabPlan').setAttribute('aria-selected', tab === 'plan');
      $('tabArchive').setAttribute('aria-selected', tab === 'archive');
      $('planToolbar').hidden = tab !== 'plan';
      $('archiveTools').hidden = tab !== 'archive';
      if(tab === 'archive'){ renderArchive(); return; }

      updateCutoff();
      $('doneTools').hidden = cutoffTotalCount === 0;
      $('doneSlider').max = cutoffTotalCount;
      $('doneSlider').value = cutoffHiddenCount;
      $('doneSlider').setAttribute('aria-valuetext', doneSliderLabel());
      $('doneSliderLabel').textContent = doneSliderLabel();

      const hiddenCount = stories.filter(isHidden).length;
      if(hiddenCount === 0) showHidden = false;
      $('hiddenTools').hidden = hiddenCount === 0 || cutoffHiddenCount > 0;
      $('toggleHidden').textContent = showHidden ? `Re-hide (${hiddenCount})` : `Show hidden (${hiddenCount})`;
      const hiddenFeatureCount = features.filter(isFeatureHidden).length;
      if(hiddenFeatureCount === 0) showHiddenFeatures = false;
      $('hiddenFeatureTools').hidden = hiddenFeatureCount === 0 || cutoffHiddenCount > 0;
      $('toggleHiddenFeatures').textContent = showHiddenFeatures ? `Re-hide features (${hiddenFeatureCount})` : `Show hidden features (${hiddenFeatureCount})`;
      $('listTools').hidden = false;
      renderFeatures();
    }

    function openStory(id){
      const s = allStories().find(x => x.id === id);
      if(!s) return;
      const f = featureOf(s.feature);
      if(activeFilter && activeFilter !== f.phase){ activeFilter = null; renderRoadmap(); $('resetPill').classList.remove('show'); }
      selected = id;
      if(s.archived){
        tab = 'archive'; archOpen.add(f.id);
        if(ARCH.phases.some(p => p.id === f.phase)) archOpen.add(f.phase);
      } else { tab = 'plan'; expanded.add(f.id); doneOpen.add(f.id); }
      renderMain();
      const el = root.querySelector('.detail');
      if(el) el.scrollIntoView({ block:'nearest' });
    }
    function closeStory(){
      selected = null; renderMain();
    }
    const setTab = t => { tab = t; selected = null; if(t === 'archive') loadArchive(); renderMain(); };

    // ---- events ----
    mainEl.addEventListener('click', e => {
      const hb = e.target.closest('[data-hide]');
      if(hb){ hiddenIds.add(hb.dataset.hide); saveHidden(); if(selected === hb.dataset.hide) selected = null; return renderMain(); }
      const ub = e.target.closest('[data-unhide]');
      if(ub){ hiddenIds.delete(ub.dataset.unhide); saveHidden(); return renderMain(); }
      const hf = e.target.closest('[data-hidefeat]');
      if(hf){ hiddenFeatureIds.add(hf.dataset.hidefeat); saveHiddenFeatures(); return renderMain(); }
      const uf = e.target.closest('[data-unhidefeat]');
      if(uf){ hiddenFeatureIds.delete(uf.dataset.unhidefeat); saveHiddenFeatures(); return renderMain(); }
      if(e.target.closest('[data-close]')) return closeStory();
      const dt = e.target.closest('[data-donetoggle]');
      if(dt){
        const id = dt.dataset.donetoggle; doneOpen.has(id) ? doneOpen.delete(id) : doneOpen.add(id);
        renderMain();
        const again = [...mainEl.querySelectorAll('[data-donetoggle]')].find(x => x.dataset.donetoggle === id);
        if(again) again.focus();
        return;
      }
      const ft = e.target.closest('[data-toggle]');
      if(ft){ const id = ft.dataset.toggle; expanded.has(id) ? expanded.delete(id) : expanded.add(id); return renderMain(); }
      const at = e.target.closest('[data-arch-toggle]');
      if(at){ const id = at.dataset.archToggle; archOpen.has(id) ? archOpen.delete(id) : archOpen.add(id); return renderArchive(); }
      const t = e.target.closest('[data-sid]');
      if(t) openStory(t.dataset.sid);
    });
    mainEl.addEventListener('keydown', e => {
      if(e.target.closest && e.target.closest('[data-hide],[data-unhide]')) return;
      const t = e.target.closest && e.target.closest('[data-sid]');
      if(t && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); openStory(t.dataset.sid); }
    });
    document.addEventListener('keydown', e => {
      if(e.key !== 'Escape') return;
      if(selected) closeStory();
    });

    $('tabPlan').addEventListener('click', () => setTab('plan'));
    $('tabArchive').addEventListener('click', () => setTab('archive'));
    $('doneSlider').addEventListener('input', e => {
      hideDoneCount = Number(e.target.value); RM.store(HIDE_DONE_COUNT_KEY, hideDoneCount);
      renderMain();
      const sel = selected && stories.find(x => x.id === selected);
      if(sel && isCutoffHiddenStory(sel)){ selected = null; renderMain(); }
    });
    $('archiveSearch').addEventListener('input', e => { archiveQuery = e.target.value; if(ARCH) renderArchive(); });
    $('toggleHidden').addEventListener('click', () => { showHidden = !showHidden; renderMain(); });
    $('unhideAll').addEventListener('click', () => { hiddenIds.clear(); showHidden = false; saveHidden(); renderMain(); });
    $('toggleHiddenFeatures').addEventListener('click', () => { showHiddenFeatures = !showHiddenFeatures; renderMain(); });
    $('unhideAllFeatures').addEventListener('click', () => { hiddenFeatureIds.clear(); showHiddenFeatures = false; saveHiddenFeatures(); renderMain(); });
    $('resetPill').addEventListener('click', () => {
      activeFilter = null; selected = null; renderRoadmap(); renderMain();
      $('resetPill').classList.remove('show');
    });
    $('expandAll').addEventListener('click', () => { features.forEach(f => { expanded.add(f.id); doneOpen.add(f.id); }); renderMain(); });
    $('collapseAll').addEventListener('click', () => { expanded.clear(); doneOpen.clear(); renderMain(); });
    $('expandCompleted').addEventListener('click', () => { visibleCompletedFeatures().forEach(f => (isDoneFeature(f) ? doneOpen : expanded).add(f.id)); renderMain(); });
    $('expandActive').addEventListener('click', () => { visibleActiveFeatures().forEach(f => expanded.add(f.id)); renderMain(); });

    renderHeader();
    renderRoadmap();
    renderMain();
  } };
})();
