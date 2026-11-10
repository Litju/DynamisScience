// RES-620 prototype E: interaction layer. Illustrative data; estimates from RES-619 receipts.
(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const css = v => getComputedStyle(document.body).getPropertyValue(v).trim();
  let seed = 11; const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const g = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const toast = msg => { const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('on'), 2200); };

  // ---------- data ----------
  const OCC = ['Pre', 'Post 0', 'Post 10m', 'Post 24h'];
  const athletes = Array.from({ length: 21 }, (_, a) => ({ id: 'A' + String(a + 1).padStart(2, '0'), base: 33 + g() * 4, sp: 3.05 + g() * .12 }));
  const rows = [];
  athletes.forEach((at, a) => OCC.forEach((o, i) => rows.push({ id: at.id, a, o, i: i + 1, h: (a === 4 || a === 15) && i === 2 ? null : +(at.base + i * .998 + g() * 1.2).toFixed(1), s: i === 0 ? +at.sp.toFixed(2) : null })));
  const trials = []; for (let q = 1; q <= 10; q++) { const b = 820 + rnd() * 420; for (let t = 1; t <= 8; t++) trials.push({ q: 'P' + q, t, f: Math.round(b + g() * 70) }); }

  // ---------- data views: by athlete (default), variables, rows ----------
  window.DS = { rows, OCC, athletes, trials };
  const hist = (vals, color) => { const v = vals.filter(x => x != null), lo = Math.min(...v), hi = Math.max(...v), n = 14, b = Array(n).fill(0);
    v.forEach(x => b[Math.min(n - 1, Math.floor((x - lo) / (hi - lo + 1e-9) * n))]++); const m = Math.max(...b);
    return `<svg viewBox="0 0 ${n * 8} 26" preserveAspectRatio="none" style="width:112px;height:22px;display:block">${b.map((c, k) => `<rect x="${k * 8 + 1}" y="${26 - c / m * 24}" width="6" height="${c / m * 24}" rx="1" fill="${color}"/>`).join('')}</svg>`; };
  const missBar = vals => { const m = vals.filter(x => x == null).length; return `<span class="mbar"><i style="width:${vals.length ? m / vals.length * 100 : 0}%"></i></span><span class="mono faint">${m ? m : '–'}</span>`; };
  const LBL = { athlete_id: 'Athlete', occasion: 'Occasion', occasion_index: 'Occasion index', cmj_height: 'CMJ height', sprint_20m: '20 m sprint', participant: 'Participant', trial: 'Trial', activity: 'Activity', peak_fz: 'Peak vertical force' };
  window.DS.LBL = LBL;
  const H = rows.map(r => r.h), S = rows.map(r => r.s), F = trials.map(r => r.f);
  const spark = (vals, step = 14) => { const v = vals.filter(x => x != null); if (v.length < 2) return ''; const lo = Math.min(...v), hi = Math.max(...v) + 1e-9, W = 8 + step * (vals.length - 1), Y = x => 17 - (x - lo) / (hi - lo) * 13;
    return `<svg viewBox="0 0 ${W} 20" style="width:${W}px;height:20px;display:block"><polyline points="${vals.map((x, i) => x == null ? '' : `${4 + i * step},${Y(x)}`).join(' ')}" fill="none" style="stroke:var(--mod)" stroke-width="1.4"/>${vals.map((x, i) => x == null ? `<circle cx="${4 + i * step}" cy="10" r="2.2" fill="none" style="stroke:var(--bad)" stroke-dasharray="1.5 1.5"/>` : `<circle cx="${4 + i * step}" cy="${Y(x)}" r="1.7" style="fill:var(--obs)"/>`).join('')}</svg>`; };
  const META = {
    lmm: { name: 'mendeley_cmj', unit: 'athlete', foot: '<span>21 athletes × 4 occasions</span><span>80 of 82 jumps</span><span class="r mono">DS-REAL-MENDELEY</span>',
      vars: [{ k: 'athlete_id', t: 'id', role: 'Subject', st: '21 athletes' }, { k: 'occasion', t: 'o', role: 'Repeated factor', st: 'Pre · Post 0 · Post 10m · Post 24h' }, { k: 'occasion_index', t: 'n', role: 'Derived from occasion (1–4)', st: 'for trend models' },
        { k: 'cmj_height', t: 'n', unit: 'cm', role: 'Outcome', vals: H }, { k: 'sprint_20m', t: 'n', unit: 's', role: 'Measured at Pre only', vals: S }],
      wide: () => { const by = athletes.map((at, a) => ({ id: at.id, v: OCC.map((_, i) => rows.find(r => r.a === a && r.i === i + 1).h), sp: at.sp }));
        return `<thead><tr><th class="rn"></th><th class="lh" data-col="athlete_id">Athlete</th>${OCC.map(o => `<th class="num lh" data-col="cmj_height">${o}<span class="u">cm</span></th>`).join('')}<th class="num lh">Δ 24 h<span class="u">cm</span></th><th class="lh">Trend</th><th class="num lh" data-col="sprint_20m">Sprint<span class="u">s · Pre</span></th></tr></thead><tbody>`
          + by.map((r, k) => { const d = r.v[3] != null && r.v[0] != null ? r.v[3] - r.v[0] : null;
            return `<tr><td class="rn">${k + 1}</td><td data-col="athlete_id"><b>${r.id}</b></td>${r.v.map(x => x == null ? '<td class="na" data-col="cmj_height" title="Missing jump">—</td>' : `<td class="num" data-col="cmj_height">${x.toFixed(1)}</td>`).join('')}<td class="num ${d > 0 ? 'pos' : 'neg'}">${d == null ? '—' : (d > 0 ? '+' : '') + d.toFixed(1)}</td><td>${spark(r.v)}</td><td class="num" data-col="sprint_20m">${r.sp.toFixed(2)}</td></tr>`; }).join('') + '</tbody>'; },
      long: () => `<thead><tr><th class="rn"></th><th class="lh" data-col="athlete_id">Athlete</th><th class="lh" data-col="occasion">Occasion</th><th class="num lh" data-col="cmj_height">CMJ height<span class="u">cm</span></th><th class="num lh" data-col="sprint_20m">Sprint<span class="u">s</span></th></tr></thead><tbody>`
        + rows.map((r, k) => `<tr><td class="rn">${k + 1}</td><td data-col="athlete_id">${r.id}</td><td data-col="occasion">${r.o}</td>${r.h == null ? '<td class="na" data-col="cmj_height">—</td>' : `<td class="num" data-col="cmj_height">${r.h.toFixed(1)}</td>`}${r.s == null ? '<td class="na" data-col="sprint_20m">—</td>' : `<td class="num" data-col="sprint_20m">${r.s.toFixed(2)}</td>`}</tr>`).join('') + '</tbody>' },
    icc: { name: 'movesmart_trials', unit: 'participant', foot: '<span>10 participants × 8 trials</span><span>Walking</span><span class="r mono">DS-REAL-MOVESMART</span>',
      vars: [{ k: 'participant', t: 'id', role: 'Subject', st: '10 participants' }, { k: 'trial', t: 'o', role: 'Repeated trial', st: '≤ 8 per participant' }, { k: 'activity', t: 'c', role: 'Filter', st: 'Walking (of 5 activities)' }, { k: 'peak_fz', t: 'n', unit: 'N', role: 'Measure', vals: F }],
      wide: () => { const ps = [...new Set(trials.map(t => t.q))];
        return `<thead><tr><th class="rn"></th><th class="lh" data-col="participant">Participant</th>${Array.from({ length: 8 }, (_, i) => `<th class="num lh" data-col="peak_fz">T${i + 1}</th>`).join('')}<th class="num lh">Mean<span class="u">N</span></th><th class="lh">Trials</th></tr></thead><tbody>`
          + ps.map((q, k) => { const v = trials.filter(t => t.q === q).map(t => t.f), m = v.reduce((a, b) => a + b, 0) / v.length;
            return `<tr><td class="rn">${k + 1}</td><td data-col="participant"><b>${q}</b></td>${v.map(x => `<td class="num" data-col="peak_fz">${x}</td>`).join('')}<td class="num"><b>${Math.round(m)}</b></td><td>${spark(v, 8)}</td></tr>`; }).join('') + '</tbody>'; },
      long: () => `<thead><tr><th class="rn"></th><th class="lh">Participant</th><th class="num lh">Trial</th><th class="lh">Activity</th><th class="num lh" data-col="peak_fz">Peak Fz<span class="u">N</span></th></tr></thead><tbody>`
        + trials.map((r, k) => `<tr><td class="rn">${k + 1}</td><td>${r.q}</td><td class="num">${r.t}</td><td>Walking</td><td class="num" data-col="peak_fz">${r.f}</td></tr>`).join('') + '</tbody>' } };
  const varsView = M => `<thead><tr><th class="lh">Variable</th><th class="lh">Type</th><th class="lh">Role</th><th class="lh">Distribution</th><th class="lh">Missing</th></tr></thead><tbody>`
    + M.vars.map(v => `<tr><td data-col="${v.k}"><div style="display:flex;gap:7px;align-items:center"><span class="ico ${v.t}">${v.t === 'id' ? 'ID' : v.t.toUpperCase()}</span><div><b>${LBL[v.k]}</b>${v.unit ? ` <span class="faint">${v.unit}</span>` : ''}<div class="mono faint" style="font-size:10.5px">${v.k}</div></div></div></td>
      <td class="muted">${{ id: 'Identifier', o: 'Ordinal', n: 'Numeric', c: 'Nominal' }[v.t]}</td><td>${v.role}</td><td>${v.vals ? hist(v.vals, v.role === 'Outcome' || v.role === 'Measure' ? 'var(--mod)' : 'var(--dim)') : `<span class="muted">${v.st}</span>`}</td><td><div style="display:flex;gap:6px;align-items:center">${missBar(v.vals || [])}</div></td></tr>`).join('') + '</tbody>';
  let current = 'lmm', selCol = null, dview = 'wide';
  const dsKey = () => current === 'icc' ? 'icc' : 'lmm';
  const renderGrid = () => { const M = META[dsKey()]; $('#grid').innerHTML = dview === 'vars' ? varsView(M) : M[dview](); $('#grid').classList.toggle('vars', dview === 'vars');
    $('#dsname').textContent = M.name; $('#dsfoot').innerHTML = M.foot; $('#dview [data-v="wide"]').textContent = M.unit === 'athlete' ? 'By athlete' : 'By participant'; paintCol(); };
  $$('#dview span').forEach(sp => sp.addEventListener('click', () => { dview = sp.dataset.v; $$('#dview span').forEach(x => x.classList.toggle('on', x === sp)); renderGrid(); }));
  const paintCol = () => $$('#grid [data-col]').forEach(c => c.classList.toggle('colsel', c.dataset.col === selCol));
  $('#grid').addEventListener('click', e => { const th = e.target.closest('th[data-col], td[data-col]'); if (!th || (th.tagName === 'TD' && dview !== 'vars')) return; selCol = selCol === th.dataset.col ? null : th.dataset.col; paintCol(); $$('.v').forEach(v => v.classList.toggle('sel', v.dataset.var === selCol)); });

  // ---------- variable assignment ----------
  const VARS = { athlete_id: 'id', occasion: 'o', occasion_index: 'n', cmj_height: 'n', sprint_20m: 'n' };
  const UNITS = { cmj_height: 'cm', sprint_20m: 's' };
  const RECORDED = { dep: ['cmj_height'], cov: ['occasion_index'], fac: [], clu: ['athlete_id'] };
  const spec = JSON.parse(JSON.stringify(RECORDED));
  const RULES = { dep: { max: 1, ok: t => t === 'n', why: 'The dependent variable must be numeric.' }, cov: { ok: t => t === 'n', why: 'Covariates must be numeric. Put categorical variables in Factors.' },
    fac: { ok: t => t === 'o' || t === 'c', why: 'Factors must be categorical or ordinal.' }, clu: { max: 1, ok: t => t === 'id', why: 'The cluster must be an identifier, such as athlete_id.' } };
  const icoHtml = t => `<span class="ico ${t}">${t === 'id' ? 'ID' : t.toUpperCase()}</span>`;
  let picked = null;
  const used = v => Object.values(spec).some(a => a.includes(v));
  const renderAssign = () => {
    $('#vlist').innerHTML = Object.entries(VARS).map(([v, t]) => `<div class="v ${used(v) ? 'used' : ''} ${picked === v ? 'sel' : ''}" draggable="true" data-var="${v}" tabindex="0">${icoHtml(t)}${v}</div>`).join('');
    $$('.tbox[data-slot]').forEach(b => b.innerHTML = spec[b.dataset.slot].map(v => `<div class="tok" draggable="true" data-var="${v}" data-from="${b.dataset.slot}">${icoHtml(VARS[v])}${v}${UNITS[v] ? ` <span class="faint">${UNITS[v]}</span>` : ''}<span class="x" title="Remove">✕</span></div>`).join(''));
    update();
  };
  const assign = (v, slot, from) => {
    const r = RULES[slot], box = $(`.tbox[data-slot="${slot}"]`);
    if (!r.ok(VARS[v])) { box.classList.remove('reject'); void box.offsetWidth; box.classList.add('reject'); toast(`${v}: ${r.why}`); return; }
    Object.keys(spec).forEach(k => spec[k] = spec[k].filter(x => x !== v));
    if (r.max === 1) spec[slot] = [v]; else spec[slot].push(v);
    picked = null; renderAssign();
  };
  document.addEventListener('dragstart', e => { const el = e.target.closest('[data-var]'); if (!el) return; e.dataTransfer.setData('text/plain', el.dataset.var); el.classList.add('dragging'); });
  document.addEventListener('dragend', e => e.target.closest?.('[data-var]')?.classList.remove('dragging'));
  $$('.tbox[data-slot]').forEach(b => {
    b.addEventListener('dragover', e => { e.preventDefault(); b.classList.add('over'); });
    b.addEventListener('dragleave', () => b.classList.remove('over'));
    b.addEventListener('drop', e => { e.preventDefault(); b.classList.remove('over'); assign(e.dataTransfer.getData('text/plain'), b.dataset.slot); });
    b.addEventListener('click', e => { if (e.target.classList.contains('x')) { const v = e.target.closest('.tok').dataset.var; spec[b.dataset.slot] = spec[b.dataset.slot].filter(x => x !== v); renderAssign(); return; } if (picked) assign(picked, b.dataset.slot); });
  });
  $('#vlist').addEventListener('dragover', e => e.preventDefault());
  $('#vlist').addEventListener('drop', e => { e.preventDefault(); const v = e.dataTransfer.getData('text/plain'); Object.keys(spec).forEach(k => spec[k] = spec[k].filter(x => x !== v)); renderAssign(); });
  $('#vlist').addEventListener('click', e => { const el = e.target.closest('.v'); if (!el) return; picked = picked === el.dataset.var ? null : el.dataset.var; renderAssign(); if (picked) toast(`Click a box to assign ${picked}, or drag it`); });
  $('#vlist').addEventListener('dblclick', e => { const el = e.target.closest('.v'); if (!el) return; const t = VARS[el.dataset.var]; assign(el.dataset.var, t === 'id' ? 'clu' : t === 'n' ? (spec.dep.length ? 'cov' : 'dep') : 'fac'); });

  // ---------- syntax + stale state ----------
  const same = () => Object.keys(RECORDED).every(k => JSON.stringify(spec[k]) === JSON.stringify(RECORDED[k]));
  let ran = true;
  const formula = () => `${spec.dep[0] || '?'} ~ ${[...spec.cov, ...spec.fac.map(f => `C(${f})`)].join(' + ') || '1'}`;
  const update = () => {
    if (current !== 'lmm') return;
    const f = formula(), clu = spec.clu[0] || '?';
    $('#syn').innerHTML = `<span class="k">smf</span>.mixedlm(<span class="s">"${f}"</span>, data, groups=data[<span class="s">"${clu}"</span>]).fit(reml=<span class="k">True</span>)  <span class="c"># TREND 1.1.0</span>`;
    $('#formula').textContent = `${f.replace(/C\((\w+)\)/g, '$1')} + (1 | ${clu})`;
    const stale = !same(); ran = !stale;
    $('#win').classList.toggle('stale-on', stale); $('#blk-norun').classList.remove('on');
    $$('.dep-spec').forEach(b => b.style.display = '');
    const rs = $('#runstate'); rs.className = 'runstate' + (stale ? ' stale' : ''); rs.lastElementChild.textContent = stale ? 'Specification changed' : 'Results up to date';
  };
  const run = () => {
    if (current !== 'lmm' || ran) return;
    const rs = $('#runstate'); rs.className = 'runstate running'; rs.lastElementChild.textContent = 'Running in worker…';
    setTimeout(() => { $('#win').classList.remove('stale-on'); ran = true;
      if (same()) { rs.className = 'runstate'; rs.lastElementChild.textContent = 'Results up to date'; return; }
      $$('.dep-spec').forEach(b => b.style.display = 'none'); $('#blk-norun').classList.add('on'); rs.className = 'runstate'; rs.lastElementChild.textContent = 'Ran · no recorded result'; }, 650);
  };
  $('#runBtn').addEventListener('click', run);
  $('#restoreBtn').addEventListener('click', () => { Object.assign(spec, JSON.parse(JSON.stringify(RECORDED))); renderAssign(); });
  $('#copySyn').addEventListener('click', () => { navigator.clipboard?.writeText($('#syn').textContent).catch(() => {}); toast('Syntax copied'); });
  $('#promote').addEventListener('click', e => { e.target.textContent = 'Already evidence: EVID-U-0002 ✓'; e.target.classList.add('done'); toast('This run is already promoted as EVID-U-0002'); });

  // ---------- options: sections + checkboxes ----------
  $$('.osec > .t').forEach(t => t.addEventListener('click', () => t.parentElement.classList.toggle('closed')));
  $$('.cb[data-show]').forEach(cb => cb.addEventListener('click', () => {
    cb.classList.toggle('on'); const el = document.getElementById(cb.dataset.show); el.classList.toggle('hide', !cb.classList.contains('on'));
    const anyFig = ['fig-resid', 'fig-qq', 'fig-re'].some(id => !document.getElementById(id).classList.contains('hide'));
    $('#blk-checks').classList.toggle('hide', !anyFig); buildOutline();
    if (cb.dataset.show === 'blk-3d' && cb.classList.contains('on')) requestAnimationFrame(draw3d);
  }));
  $$('.cb.dis').forEach(cb => cb.addEventListener('click', () => toast('Cook\'s distance is not available for the qualified mixed-model method')));

  // ---------- analysis switch ----------
  const resKey = () => ['lmm', 'icc'].includes(current) ? current : 'gen';
  const setAnalysis = an => { current = an; const gen = !['lmm', 'icc'].includes(an);
    P.go(gen ? 'an-gen' : 'an-' + an, 'opt'); P.go(gen ? 'res-gen' : 'res-' + an, 'res'); $$('.rb[data-an]').forEach(b => b.classList.toggle('on', b.dataset.an === an)); selCol = null; renderGrid();
    if (gen) { $('#win').classList.remove('stale-on'); $('#runstate').className = 'runstate'; $('#runstate').lastElementChild.textContent = 'Results up to date'; window.GEN.show(an); }
    else if (an === 'icc') { $('#syn').innerHTML = `<span class="k">reliability</span>.icc(data, measure=<span class="s">"peak_fz"</span>, subject=<span class="s">"participant"</span>, trial=<span class="s">"trial"</span>, form=<span class="s">"3,1"</span>)  <span class="c"># RELIABILITY 1.1.0</span>`; $('#win').classList.remove('stale-on'); $('#runstate').className = 'runstate'; $('#runstate').lastElementChild.textContent = 'Results up to date'; }
    else { update(); requestAnimationFrame(draw3d); } buildOutline(); };
  $$('.rb').forEach(b => b.addEventListener('click', () => b.dataset.an ? setAnalysis(b.dataset.an) : toast(`${b.title}: not drawn in this prototype`)));

  // ---------- theme ----------
  const setTheme = t => { document.body.dataset.theme = t; $$('#theme span').forEach(s => s.classList.toggle('on', s.dataset.t === t)); requestAnimationFrame(draw3d); };
  $$('#theme span').forEach(s => s.addEventListener('click', () => setTheme(s.dataset.t)));

  // ---------- splitters ----------
  $$('.split').forEach(sp => sp.addEventListener('pointerdown', e => {
    sp.classList.add('drag'); sp.setPointerCapture(e.pointerId); const panes = $('#panes'), cols = [...panes.children].filter(c => c.classList.contains('pane')).map(c => c.getBoundingClientRect().width);
    const x0 = e.clientX, k = +sp.dataset.split;
    const mv = ev => { const dx = ev.clientX - x0; const a = Math.max(300, cols[k - 1] + dx), b = Math.max(260, cols[k] - dx);
      if (k === 1) { panes.style.setProperty('--c1', a + 'px'); panes.style.setProperty('--c2', b + 'px'); panes.style.setProperty('--c3', '1fr'); } else { panes.style.setProperty('--c1', cols[0] + 'px'); panes.style.setProperty('--c2', a + 'px'); panes.style.setProperty('--c3', '1fr'); } draw3d(); };
    const up = () => { sp.classList.remove('drag'); sp.removeEventListener('pointermove', mv); sp.removeEventListener('pointerup', up); };
    sp.addEventListener('pointermove', mv); sp.addEventListener('pointerup', up);
  }));

  // ---------- outline ----------
  const buildOutline = () => { const blocks = $$('#res-' + resKey() + ' .rblock').filter(b => !b.classList.contains('hide') && !b.classList.contains('noresult'));
    $('#outline').innerHTML = blocks.map((b, i) => `<div data-i="${i}">${b.querySelector('.rtitle').childNodes[0].textContent.trim()}</div>`).join('');
    $$('#outline div').forEach(d => d.addEventListener('click', () => { blocks[+d.dataset.i].scrollIntoView({ block: 'start' }); $('#outline').classList.remove('on'); })); };
  $('#outlineBtn').addEventListener('click', e => { e.stopPropagation(); buildOutline(); $('#outline').classList.toggle('on'); });
  document.addEventListener('click', e => { if (!e.target.closest('#outline')) $('#outline').classList.remove('on'); });

  // ---------- command palette ----------
  const CMDS = () => [
    { t: 'Run analysis', g: 'Ctrl ↵', f: run }, { t: 'Mixed Models', g: 'Analysis', f: () => setAnalysis('lmm') }, { t: 'Reliability (ICC)', g: 'Analysis', f: () => setAnalysis('icc') },
    ...[['desc', 'Descriptives'], ['ttest', 'Paired samples T-Test'], ['anova', 'Repeated measures ANOVA'], ['reg', 'Linear regression'], ['freq', 'Frequencies'], ['change', 'Athlete change']].map(([k, t]) => ({ t, g: 'Analysis', f: () => setAnalysis(k) })),
    { t: 'Data: by athlete', g: 'Data', f: () => $('#dview [data-v="wide"]').click() }, { t: 'Data: variables', g: 'Data', f: () => $('#dview [data-v="vars"]').click() }, { t: 'Data: rows', g: 'Data', f: () => $('#dview [data-v="long"]').click() },
    ...Object.keys(VARS).filter(v => RULES.dep.ok(VARS[v])).map(v => ({ t: `Assign ${v} as dependent`, g: 'Variable', f: () => assign(v, 'dep') })),
    ...Object.keys(VARS).filter(v => RULES.cov.ok(VARS[v])).map(v => ({ t: `Add ${v} to covariates`, g: 'Variable', f: () => assign(v, 'cov') })),
    ...Object.keys(VARS).filter(v => RULES.fac.ok(VARS[v])).map(v => ({ t: `Add ${v} as factor`, g: 'Variable', f: () => assign(v, 'fac') })),
    { t: 'Show random-effect distribution', g: 'Assumption', f: () => $('.cb[data-show="fig-re"]').click() },
    { t: 'Toggle dark theme', g: 'View', f: () => setTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark') },
    { t: 'Restore recorded specification', g: 'Model', f: () => $('#restoreBtn').click() }, { t: 'Copy syntax', g: 'Results', f: () => $('#copySyn').click() } ];
  let palSel = 0, palList = [];
  const palRender = () => { const q = $('#palin').value.toLowerCase(); palList = CMDS().filter(c => c.t.toLowerCase().includes(q)).slice(0, 9); palSel = Math.min(palSel, Math.max(0, palList.length - 1));
    $('#palitems').innerHTML = palList.map((c, i) => `<div class="it ${i === palSel ? 'on' : ''}" data-i="${i}">${c.t}<span class="g">${c.g}</span></div>`).join('') || '<div class="it muted">No match</div>';
    $$('#palitems .it[data-i]').forEach(d => d.addEventListener('click', () => { closePal(); palList[+d.dataset.i].f(); })); };
  const openPal = (q = '') => { $('#palbg').classList.add('on'); $('#palin').value = q; palSel = 0; palRender(); $('#palin').focus(); };
  const closePal = () => $('#palbg').classList.remove('on');
  $('#openPalette').addEventListener('click', () => openPal());
  $('#palin').addEventListener('input', () => { palSel = 0; palRender(); });
  $('#palbg').addEventListener('click', e => { if (e.target.id === 'palbg') closePal(); });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPal(); }
    else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    else if ($('#palbg').classList.contains('on')) {
      if (e.key === 'Escape') closePal(); else if (e.key === 'ArrowDown') { palSel = Math.min(palSel + 1, palList.length - 1); palRender(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { palSel = Math.max(palSel - 1, 0); palRender(); e.preventDefault(); } else if (e.key === 'Enter' && palList[palSel]) { closePal(); palList[palSel].f(); } }
  });

  // ---------- 3D trajectories ----------
  const cv = $('#c3d'), ctx = cv.getContext('2d'), stage = $('#stage3d'), tip = $('#tip3d');
  const order = athletes.map((a, i) => i).sort((p, q) => athletes[p].base - athletes[q].base); const rank = []; order.forEach((a, r) => rank[a] = r);
  const N = (o, a, h) => [o / 3 * 2 - 1, (h - 24) / 20 * 2 - 1, rank[a] / 20 * 2 - 1];
  const layers = { pts: true, surf: true, lines: false };
  let cam = { yaw: -1.0, pitch: 0.32, zoom: 1 }, target = { yaw: -0.68, pitch: 0.32, zoom: 1 }, hover = null, proj = [];
  const P3 = ([x, y, z]) => { const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw), cp = Math.cos(cam.pitch), spn = Math.sin(cam.pitch);
    const x1 = x * cy - z * sy, z1 = x * sy + z * cy, y2 = y * cp - z1 * spn, z2 = y * spn + z1 * cp; const W = cv.width, Hh = cv.height, s = Math.min(W, Hh) * .33 * cam.zoom, f = 4 / (4 + z2);
    return [W / 2 + x1 * s * f, Hh / 2 - 6 * devicePixelRatio - y2 * s * f, z2]; };
  function draw3d() {
    if (!cv.offsetParent) return;
    const dpr = devicePixelRatio || 1; cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr; ctx.clearRect(0, 0, cv.width, cv.height);
    const C = { line: css('--line2'), grid: css('--line'), dim: css('--dim'), obs: css('--obs'), mod: css('--mod'), text: css('--text') };
    ctx.lineWidth = dpr; ctx.font = `${11 * dpr}px Segoe UI`;
    const seg = (a, b, col, w = 1) => { const p = P3(a), q = P3(b); ctx.strokeStyle = col; ctx.lineWidth = w * dpr; ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); };
    const label = (pt, txt, col = C.dim, align = 'center') => { const p = P3(pt); ctx.fillStyle = col; ctx.textAlign = align; ctx.fillText(txt, p[0], p[1]); };
    // floor grid and back walls
    for (let i = 0; i <= 3; i++) { const x = i / 3 * 2 - 1; seg([x, -1, -1], [x, -1, 1], C.grid); label([x, -1.18, 1.12], OCC[i]); }
    for (let k = 0; k <= 4; k++) { const z = k / 4 * 2 - 1; seg([-1, -1, z], [1, -1, z], C.grid); }
    for (let v = 24; v <= 44; v += 5) { const y = (v - 24) / 20 * 2 - 1; seg([-1, y, -1], [1, y, -1], C.grid); seg([-1, y, -1], [-1, y, 1], C.grid); label([-1.06, y - .02, -1.06], String(v), C.dim, 'right'); }
    [[-1, -1, -1], [1, -1, -1], [1, -1, 1], [-1, -1, 1]].forEach((p, i, A) => seg(p, A[(i + 1) % 4], C.line, 1.2));
    seg([-1, -1, -1], [-1, 1, -1], C.line, 1.2);
    label([0, -1.38, 1.2], 'Occasion', C.text); label([1.28, -1.1, 0], 'Athlete (by baseline)', C.text); label([-1.06, 1.16, -1.06], 'CMJ height (cm)', C.text, 'center');
    // model surface: fixed-effect slope plus each athlete's intercept
    const faces = [];
    if (layers.surf) for (let r = 0; r < 20; r++) for (let o = 0; o < 3; o++) { const a1 = order[r], a2 = order[r + 1];
      const q = [N(o, a1, athletes[a1].base + o * .998), N(o + 1, a1, athletes[a1].base + (o + 1) * .998), N(o + 1, a2, athletes[a2].base + (o + 1) * .998), N(o, a2, athletes[a2].base + o * .998)].map(P3);
      const zc = q.reduce((s, p) => s + p[2], 0) / 4, hv = ((athletes[a1].base + o * .998) - 26) / 16; faces.push({ q, zc, hv }); }
    faces.sort((p, q) => q.zc - p.zc).forEach(fc => { ctx.beginPath(); fc.q.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath();
      ctx.globalAlpha = .16 + Math.max(0, Math.min(1, fc.hv)) * .26; ctx.fillStyle = C.mod; ctx.fill(); ctx.globalAlpha = .35; ctx.strokeStyle = C.mod; ctx.lineWidth = .6 * dpr; ctx.stroke(); ctx.globalAlpha = 1; });
    if (layers.lines) athletes.forEach((at, a) => { const pts = rows.filter(r => r.a === a && r.h != null).map(r => P3(N(r.i - 1, a, r.h))); ctx.strokeStyle = C.obs; ctx.globalAlpha = .45; ctx.lineWidth = dpr; ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke(); ctx.globalAlpha = 1; });
    proj = [];
    if (layers.pts) { rows.filter(r => r.h != null).map(r => ({ r, p: P3(N(r.i - 1, r.a, r.h)) })).sort((u, v) => v.p[2] - u.p[2]).forEach(({ r, p }) => {
      const rad = (2.6 + (1 - p[2]) * .9) * dpr, on = hover === r; ctx.beginPath(); ctx.arc(p[0], p[1], on ? rad * 1.8 : rad, 0, 7); ctx.fillStyle = C.obs; ctx.globalAlpha = on ? 1 : .55 + (1 - p[2]) * .2; ctx.fill(); ctx.globalAlpha = 1;
      if (on) { ctx.strokeStyle = C.mod; ctx.lineWidth = 2 * dpr; ctx.stroke(); } proj.push({ r, x: p[0] / dpr, y: p[1] / dpr }); }); }
  }
  const animate = () => { let moving = false; for (const k of ['yaw', 'pitch', 'zoom']) { const d = target[k] - cam[k]; if (Math.abs(d) > 1e-3) { cam[k] += d * .12; moving = true; } else cam[k] = target[k]; } draw3d(); if (moving) requestAnimationFrame(animate); };
  let drag = null;
  stage.addEventListener('pointerdown', e => { if (e.target.closest('button')) return; drag = { x: e.clientX, y: e.clientY, yaw: target.yaw, pitch: target.pitch }; stage.setPointerCapture(e.pointerId); $$('.hud2 .mini').forEach(b => b.classList.remove('on')); });
  stage.addEventListener('pointermove', e => {
    if (drag) { target.yaw = drag.yaw + (e.clientX - drag.x) * .008; target.pitch = Math.max(-0.1, Math.min(1.35, drag.pitch + (e.clientY - drag.y) * .006)); cam.yaw = target.yaw; cam.pitch = target.pitch; draw3d(); tip.style.display = 'none'; return; }
    const b = cv.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top; let best = null, bd = 100;
    proj.forEach(p => { const d = (p.x - mx) ** 2 + (p.y - my) ** 2; if (d < bd) { bd = d; best = p; } });
    const nh = best ? best.r : null; if (nh !== hover) { hover = nh; draw3d(); }
    if (best) { tip.style.display = 'block'; tip.style.left = best.x + 'px'; tip.style.top = best.y + 'px'; tip.textContent = `${best.r.id} · ${best.r.o} · ${best.r.h.toFixed(1)} cm (observed)`; } else tip.style.display = 'none';
  });
  stage.addEventListener('pointerup', () => drag = null);
  stage.addEventListener('pointerleave', () => { hover = null; tip.style.display = 'none'; draw3d(); });
  stage.addEventListener('wheel', e => { e.preventDefault(); target.zoom = Math.max(.6, Math.min(2.2, target.zoom * (e.deltaY < 0 ? 1.08 : .93))); animate(); }, { passive: false });
  $$('.hud .mini').forEach(b => b.addEventListener('click', () => { layers[b.dataset.l] = !layers[b.dataset.l]; b.classList.toggle('on', layers[b.dataset.l]); draw3d(); }));
  const VIEWS = { front: { yaw: 0, pitch: 0 }, side: { yaw: -Math.PI / 2, pitch: 0 }, iso: { yaw: -0.68, pitch: 0.32 } };
  $$('.hud2 .mini').forEach(b => b.addEventListener('click', () => { Object.assign(target, VIEWS[b.dataset.view]); $$('.hud2 .mini').forEach(x => x.classList.toggle('on', x === b)); animate(); }));
  addEventListener('resize', draw3d);

  // ---------- boot ----------
  window.APP = { toast, buildOutline, setAnalysis };
  renderAssign(); renderGrid(); buildOutline();
  addEventListener('load', () => {
    const h = location.hash.slice(1).split(',');
    if (h.includes('dark')) setTheme('dark');
    const an = ['icc', 'desc', 'ttest', 'anova', 'reg', 'freq', 'change', 'signals'].find(k => h.includes(k)); if (an) setAnalysis(an);
    const dv = ['vars', 'long'].find(k => h.includes(k)); if (dv) $(`#dview [data-v="${dv}"]`).click();
    if (h.includes('stale')) { spec.cov = []; spec.fac = ['occasion']; renderAssign(); }
    if (h.includes('re')) $('.cb[data-show="fig-re"]').click();
    if (h.includes('3d')) { const R = $('#results'); R.style.scrollBehavior = 'auto'; R.scrollTop = $('#blk-3d').offsetTop - 14; }
    if (h.includes('palette')) openPal('assign');
    if (h.includes('col')) { selCol = 'cmj_height'; paintCol(); }
    animate();
  });
})();
