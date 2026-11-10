// RES-620 prototype E: generic analyses computed live from the prototype's illustrative data.
// None of these are recorded runs; every result block says so.
(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const { rows, OCC, LBL } = window.DS;
  const APP = () => window.APP;

  // ---------- statistics ----------
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  const sd = a => { const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
  const quant = (a, p) => { const s = [...a].sort((x, y) => x - y), i = (s.length - 1) * p, l = Math.floor(i); return s[l] + (s[Math.ceil(i)] - s[l]) * (i - l); };
  function lgamma(x) { const c = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, .1208650973866179e-2, -.5395239384953e-5];
    let y = x, t = x + 5.5; t -= (x + .5) * Math.log(t); let s = 1.000000000190015; for (const k of c) s += k / ++y; return -t + Math.log(2.5066282746310005 * s / x); }
  function betacf(a, b, x) { const tiny = 1e-30; let c = 1, d = 1 - (a + b) * x / (a + 1); if (Math.abs(d) < tiny) d = tiny; d = 1 / d; let h = d;
    for (let m = 1; m <= 300; m++) { const m2 = 2 * m; let aa = m * (b - m) * x / ((a - 1 + m2) * (a + m2)); d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d; h *= d * c;
      aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + 1 + m2)); d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d; const del = d * c; h *= del; if (Math.abs(del - 1) < 3e-14) break; } return h; }
  function ibeta(x, a, b) { if (x <= 0) return 0; if (x >= 1) return 1; const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
    return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b; }
  const pT = (t, df) => ibeta(df / (df + t * t), df / 2, .5);              // two-sided
  const pF = (F, d1, d2) => ibeta(d2 / (d2 + d1 * F), d2 / 2, d1 / 2);      // upper tail
  const tcrit = (df, alpha = .05) => { let lo = 0, hi = 60; for (let i = 0; i < 70; i++) { const m = (lo + hi) / 2; pT(m, df) > alpha ? lo = m : hi = m; } return (lo + hi) / 2; };
  const fp = p => p < .001 ? '&lt; .001' : p.toFixed(3).replace(/^0/, '');
  const f = (x, d = 2) => (x < 0 ? '−' : '') + Math.abs(x).toFixed(d);
  const inv = M => { const n = M.length, A = M.map((r, i) => [...r, ...Array.from({ length: n }, (_, j) => +(i === j))]);
    for (let i = 0; i < n; i++) { let p = i; for (let r = i + 1; r < n; r++) if (Math.abs(A[r][i]) > Math.abs(A[p][i])) p = r; [A[i], A[p]] = [A[p], A[i]];
      const d = A[i][i]; if (Math.abs(d) < 1e-12) return null; for (let j = 0; j < 2 * n; j++) A[i][j] /= d;
      for (let r = 0; r < n; r++) if (r !== i) { const k = A[r][i]; for (let j = 0; j < 2 * n; j++) A[r][j] -= k * A[i][j]; } } return A.map(r => r.slice(n)); };
  // self-check against known values: t=2.086 at df=20 gives p≈.05; F(1,10)=4.965 gives p≈.05
  console.assert(Math.abs(pT(2.086, 20) - .05) < 1e-3 && Math.abs(pF(4.965, 1, 10) - .05) < 1e-3, 'stats self-check failed');

  // ---------- data access ----------
  const VARS = { athlete_id: 'id', occasion: 'o', occasion_index: 'n', cmj_height: 'n', sprint_20m: 'n' };
  const UNIT = { cmj_height: 'cm', sprint_20m: 's' };
  const val = (r, k) => ({ athlete_id: r.id, occasion: r.o, occasion_index: r.i, cmj_height: r.h, sprint_20m: r.s })[k];
  const levels = k => k === 'occasion' ? OCC : k === 'occasion_index' ? [1, 2, 3, 4] : [...new Set(rows.map(r => val(r, k)))];
  const lab = k => `${LBL[k]}${UNIT[k] ? ` (${UNIT[k]})` : ''}`;

  // ---------- plotting (theme-aware through CSS variables) ----------
  const niceStep = (span, n) => { const raw = span / n, p = 10 ** Math.floor(Math.log10(raw)), m = raw / p; return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p; };
  const ticks = (lo, hi, n = 5) => { const st = niceStep(hi - lo, n), out = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(10)); return out; };
  const pad = (lo, hi, k = .08) => { const d = (hi - lo) || 1; return [lo - d * k, hi + d * k]; };
  function frame(w, h, { xr, yr, xl, yl, xcat, xnum }) {
    const m = { l: 50, r: 14, t: 12, b: 38 }, sx = v => m.l + (v - xr[0]) / (xr[1] - xr[0]) * (w - m.l - m.r), sy = v => h - m.b - (v - yr[0]) / (yr[1] - yr[0]) * (h - m.t - m.b);
    let s = `<svg viewBox="0 0 ${w} ${h}" style="width:100%;display:block" font-family="Segoe UI" font-size="11">`;
    ticks(yr[0], yr[1]).forEach(v => s += `<line x1="${m.l}" x2="${w - m.r}" y1="${sy(v)}" y2="${sy(v)}" style="stroke:var(--line)"/><text x="${m.l - 7}" y="${sy(v) + 3.5}" text-anchor="end" style="fill:var(--dim)">${+v.toFixed(3)}</text>`);
    (xcat || []).forEach((l, i) => s += `<text x="${sx(i)}" y="${h - m.b + 16}" text-anchor="middle" style="fill:var(--dim)">${l}</text>`);
    if (xnum) ticks(xr[0], xr[1]).forEach(v => s += `<text x="${sx(v)}" y="${h - m.b + 16}" text-anchor="middle" style="fill:var(--dim)">${+v.toFixed(3)}</text>`);
    s += `<line x1="${m.l}" x2="${w - m.r}" y1="${h - m.b}" y2="${h - m.b}" style="stroke:var(--line2)"/>`;
    if (xl) s += `<text x="${(m.l + w - m.r) / 2}" y="${h - 5}" text-anchor="middle" style="fill:var(--dim)">${xl}</text>`;
    if (yl) s += `<text transform="translate(13 ${(h - m.b + m.t) / 2}) rotate(-90)" text-anchor="middle" style="fill:var(--dim)">${yl}</text>`;
    return { s, sx, sy, m, w, h, end: () => '</svg>' };
  }
  const jit = i => ((i * 7919) % 13 - 6) / 6;
  function boxPlot(groups, names, yl) {
    const all = groups.flat(), F = frame(560, 250, { xr: [-.6, groups.length - .4], yr: pad(Math.min(...all), Math.max(...all)), xl: '', yl, xcat: names }); let s = F.s;
    groups.forEach((g, i) => { if (!g.length) return; const q1 = quant(g, .25), q2 = quant(g, .5), q3 = quant(g, .75), iqr = q3 - q1, lo = Math.min(...g.filter(v => v >= q1 - 1.5 * iqr)), hi = Math.max(...g.filter(v => v <= q3 + 1.5 * iqr)), x = F.sx(i), bw = 34;
      s += `<line x1="${x}" x2="${x}" y1="${F.sy(lo)}" y2="${F.sy(hi)}" style="stroke:var(--dim)"/><rect x="${x - bw / 2}" y="${F.sy(q3)}" width="${bw}" height="${F.sy(q1) - F.sy(q3)}" rx="3" style="fill:color-mix(in srgb,var(--mod) 14%,transparent);stroke:var(--mod)"/><line x1="${x - bw / 2}" x2="${x + bw / 2}" y1="${F.sy(q2)}" y2="${F.sy(q2)}" style="stroke:var(--mod)" stroke-width="2.2"/>`;
      g.forEach((v, k) => s += `<circle cx="${x + 30 + jit(k) * 7}" cy="${F.sy(v)}" r="2.3" style="fill:var(--obs)" opacity=".6"/>`); });
    return s + F.end(); }
  function histPlot(v, xl) { const lo = Math.min(...v), hi = Math.max(...v), n = 10, st = (hi - lo) / n || 1, b = Array(n).fill(0); v.forEach(x => b[Math.min(n - 1, Math.floor((x - lo) / st))]++);
    const F = frame(560, 220, { xr: [lo, hi], yr: [0, Math.max(...b) * 1.15], xl, yl: 'Count', xnum: true }); let s = F.s;
    b.forEach((c, k) => s += `<rect x="${F.sx(lo + k * st) + 1}" y="${F.sy(c)}" width="${F.sx(lo + st) - F.sx(lo) - 2}" height="${F.sy(0) - F.sy(c)}" rx="2" style="fill:color-mix(in srgb,var(--obs) 70%,transparent)"/>`); return s + F.end(); }
  function slopePlot(pairs, a, b, yl) { const all = pairs.flat(), F = frame(560, 260, { xr: [-.35, 1.35], yr: pad(Math.min(...all), Math.max(...all)), yl, xcat: [] }); let s = F.s;
    s += `<text x="${F.sx(0)}" y="${F.h - F.m.b + 16}" text-anchor="middle" style="fill:var(--dim)">${a}</text><text x="${F.sx(1)}" y="${F.h - F.m.b + 16}" text-anchor="middle" style="fill:var(--dim)">${b}</text>`;
    pairs.forEach(([u, v]) => s += `<line x1="${F.sx(0)}" x2="${F.sx(1)}" y1="${F.sy(u)}" y2="${F.sy(v)}" style="stroke:${v >= u ? 'var(--obs)' : 'var(--bad)'}" stroke-opacity=".35"/><circle cx="${F.sx(0)}" cy="${F.sy(u)}" r="2.6" style="fill:var(--obs)"/><circle cx="${F.sx(1)}" cy="${F.sy(v)}" r="2.6" style="fill:var(--obs)"/>`);
    const ma = mean(pairs.map(p => p[0])), mb = mean(pairs.map(p => p[1]));
    s += `<line x1="${F.sx(0)}" x2="${F.sx(1)}" y1="${F.sy(ma)}" y2="${F.sy(mb)}" style="stroke:var(--mod)" stroke-width="3"/><circle cx="${F.sx(0)}" cy="${F.sy(ma)}" r="5" style="fill:var(--mod)"/><circle cx="${F.sx(1)}" cy="${F.sy(mb)}" r="5" style="fill:var(--mod)"/>`;
    return s + F.end(); }
  function meansPlot(ms, cis, names, yl) { const lo = Math.min(...ms.map((m, i) => m - cis[i])), hi = Math.max(...ms.map((m, i) => m + cis[i])), F = frame(560, 240, { xr: [-.5, ms.length - .5], yr: pad(lo, hi, .25), yl, xcat: names }); let s = F.s;
    s += `<polyline points="${ms.map((m, i) => `${F.sx(i)},${F.sy(m)}`).join(' ')}" fill="none" style="stroke:var(--mod)" stroke-width="2"/>`;
    ms.forEach((m, i) => s += `<line x1="${F.sx(i)}" x2="${F.sx(i)}" y1="${F.sy(m - cis[i])}" y2="${F.sy(m + cis[i])}" style="stroke:var(--mod)" stroke-width="2"/><line x1="${F.sx(i) - 6}" x2="${F.sx(i) + 6}" y1="${F.sy(m - cis[i])}" y2="${F.sy(m - cis[i])}" style="stroke:var(--mod)"/><line x1="${F.sx(i) - 6}" x2="${F.sx(i) + 6}" y1="${F.sy(m + cis[i])}" y2="${F.sy(m + cis[i])}" style="stroke:var(--mod)"/><circle cx="${F.sx(i)}" cy="${F.sy(m)}" r="5" style="fill:var(--base);stroke:var(--mod)" stroke-width="2"/>`);
    return s + F.end(); }
  function scatterFit(x, y, b0, b1, seFit, xl, yl) { const F = frame(560, 260, { xr: pad(Math.min(...x), Math.max(...x)), yr: pad(Math.min(...y), Math.max(...y), .15), xl, yl, xnum: true }); let s = F.s;
    const X0 = pad(Math.min(...x), Math.max(...x)), grid = Array.from({ length: 30 }, (_, i) => X0[0] + (X0[1] - X0[0]) * i / 29);
    const up = grid.map(g => `${F.sx(g)},${F.sy(b0 + b1 * g + seFit(g))}`), dn = grid.map(g => `${F.sx(g)},${F.sy(b0 + b1 * g - seFit(g))}`).reverse();
    s += `<polygon points="${up.concat(dn).join(' ')}" style="fill:color-mix(in srgb,var(--mod) 14%,transparent)"/><line x1="${F.sx(X0[0])}" x2="${F.sx(X0[1])}" y1="${F.sy(b0 + b1 * X0[0])}" y2="${F.sy(b0 + b1 * X0[1])}" style="stroke:var(--mod)" stroke-width="2.2"/>`;
    x.forEach((v, i) => s += `<circle cx="${F.sx(v)}" cy="${F.sy(y[i])}" r="3" style="fill:var(--obs)" opacity=".75"/>`); return s + F.end(); }
  function residPlot(fit, res) { const F = frame(560, 220, { xr: pad(Math.min(...fit), Math.max(...fit)), yr: pad(Math.min(...res), Math.max(...res), .2), xl: 'Fitted', yl: 'Residual', xnum: true }); let s = F.s;
    s += `<line x1="${F.m.l}" x2="${F.w - F.m.r}" y1="${F.sy(0)}" y2="${F.sy(0)}" style="stroke:var(--dim)" stroke-dasharray="4 3"/>`; fit.forEach((v, i) => s += `<circle cx="${F.sx(v)}" cy="${F.sy(res[i])}" r="3" style="fill:var(--mod)" opacity=".75"/>`); return s + F.end(); }
  function barPlot(names, counts) { const F = frame(560, 220, { xr: [-.6, names.length - .4], yr: [0, Math.max(...counts) * 1.2], yl: 'Count', xcat: names.length <= 8 ? names : [] }); let s = F.s; const bw = Math.min(46, (F.sx(1) - F.sx(0)) * .7);
    counts.forEach((c, i) => s += `<rect x="${F.sx(i) - bw / 2}" y="${F.sy(c)}" width="${bw}" height="${F.sy(0) - F.sy(c)}" rx="3" style="fill:color-mix(in srgb,var(--obs) 70%,transparent)"/>`); return s + F.end(); }
  function changeBars(items, thr) { const ext = Math.max(...items.map(i => Math.abs(i.d)), thr || 0) * 1.15, h = 26 + items.length * 17, w = 560, l = 52, r = 60, sx = v => l + (v + ext) / (2 * ext) * (w - l - r);
    let s = `<svg viewBox="0 0 ${w} ${h + 26}" style="width:100%;display:block" font-family="Segoe UI" font-size="11">`;
    if (thr) s += `<rect x="${sx(-thr)}" y="8" width="${sx(thr) - sx(-thr)}" height="${h - 8}" style="fill:color-mix(in srgb,var(--dim) 12%,transparent)"/><text x="${sx(thr) + 4}" y="18" style="fill:var(--dim)">±${thr} SWC</text>`;
    s += `<line x1="${sx(0)}" x2="${sx(0)}" y1="6" y2="${h}" style="stroke:var(--line2)"/>`;
    items.forEach((it, i) => { const y = 16 + i * 17, beyond = thr && Math.abs(it.d) > thr; s += `<text x="${l - 8}" y="${y + 4}" text-anchor="end" style="fill:var(--muted)">${it.id}</text><rect x="${Math.min(sx(0), sx(it.d))}" y="${y - 5}" width="${Math.abs(sx(it.d) - sx(0))}" height="10" rx="2" style="fill:${beyond ? (it.d > 0 ? 'var(--ok)' : 'var(--bad)') : 'color-mix(in srgb,var(--obs) 55%,transparent)'}"/><text x="${sx(it.d) + (it.d >= 0 ? 6 : -6)}" y="${y + 4}" text-anchor="${it.d >= 0 ? 'start' : 'end'}" style="fill:var(--dim)" font-family="Cascadia Mono, Consolas" font-size="10">${(it.d > 0 ? '+' : '') + it.d.toFixed(1)}</text>`; });
    ticks(-ext, ext).forEach(v => s += `<text x="${sx(v)}" y="${h + 16}" text-anchor="middle" style="fill:var(--dim)">${+v.toFixed(2)}</text>`);
    return s + '</svg>'; }

  // ---------- result helpers ----------
  const PROTO = '<span class="chip s-unav" title="Computed live in the prototype from illustrative values. Not a recorded run.">ILLUSTRATIVE DATA</span>';
  const block = (title, chips, body, foot) => `<div class="rblock"><div class="rtitle">${title} ${chips}</div>${body}${foot ? `<div class="rfoot">${foot}</div>` : ''}</div>`;
  const table = (caption, head, rowsH, numFrom = 1) => `<table class="apa"><caption>${caption}</caption><thead><tr>${head.map((h, i) => `<th class="${i >= numFrom ? 'num' : ''}">${h}</th>`).join('')}</tr></thead><tbody>${rowsH.map(r => `<tr>${r.map((c, i) => `<td class="${i >= numFrom ? 'num' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const empty = msg => `<div class="rblock"><div class="rtitle">Waiting for variables</div><p class="muted" style="margin:8px 0 0">${msg}</p></div>`;
  const notQualified = '<span class="chip s-expl" title="Not in the qualified method catalogue. Use for exploration only.">NOT QUALIFIED</span>';
  const plotWrap = (svg, cap) => `<div class="plot" style="max-width:620px;margin-top:10px">${svg}${cap ? `<div class="cap">${cap}</div>` : ''}</div>`;
  const byLevel = (out, wi, su) => { const m = {}; rows.forEach(r => { const y = val(r, out); if (y == null) return; const s = val(r, su); (m[s] = m[s] || {})[val(r, wi)] = y; }); return m; };

  // ---------- analysis definitions ----------
  const S = { n: 'numeric', o: 'ordinal', c: 'nominal', id: 'identifier' };
  const DEF = {
    desc: { title: 'Descriptives', status: '<span class="chip s-desc">DESCRIPTIVE</span>', method: 'pandas describe',
      slots: [{ k: 'vars', label: 'Variables', rule: 'numeric', ok: t => t === 'n' }, { k: 'split', label: 'Split by', rule: '1 categorical', max: 1, ok: t => t === 'o' || t === 'c' }],
      spec: { vars: ['cmj_height'], split: ['occasion'] },
      sections: [{ t: 'Statistics', items: [['n', 'N and missing', 1], ['mean', 'Mean and SD', 1], ['median', 'Median and IQR', 1], ['range', 'Minimum and maximum', 0], ['ci', '95% CI of the mean', 0]] }, { t: 'Plots', items: [['box', 'Box plot with points', 1], ['hist', 'Histogram', 0]] }],
      syntax: (s) => `data.groupby(<span class="s">"${s.split[0] || ''}"</span>)[[${s.vars.map(v => `<span class="s">"${v}"</span>`).join(', ')}]].describe()`,
      run(s, o) { if (!s.vars.length) return empty('Drag one or more numeric variables into <b>Variables</b>.');
        const lv = s.split[0] ? levels(s.split[0]) : ['All'], head = ['Variable', s.split[0] ? LBL[s.split[0]] : ''].concat(o.n ? ['N', 'Missing'] : [], o.mean ? ['Mean', 'SD'] : [], o.median ? ['Median', 'IQR'] : [], o.range ? ['Min', 'Max'] : [], o.ci ? ['95% CI'] : []);
        const out = []; s.vars.forEach(v => lv.forEach((l, i) => { const all = rows.filter(r => !s.split[0] || val(r, s.split[0]) === l).map(r => val(r, v)), x = all.filter(a => a != null); if (!x.length) return;
          const m = mean(x), d = x.length > 1 ? sd(x) : 0, ci = x.length > 1 ? tcrit(x.length - 1) * d / Math.sqrt(x.length) : 0;
          out.push([i ? '' : `<b>${lab(v)}</b>`, s.split[0] ? l : ''].concat(o.n ? [x.length, all.length - x.length] : [], o.mean ? [f(m), f(d)] : [], o.median ? [f(quant(x, .5)), f(quant(x, .75) - quant(x, .25))] : [], o.range ? [f(Math.min(...x)), f(Math.max(...x))] : [], o.ci ? [`${f(m - ci)} – ${f(m + ci)}`] : [])); }));
        const v0 = s.vars[0], groups = lv.map(l => rows.filter(r => !s.split[0] || val(r, s.split[0]) === l).map(r => val(r, v0)).filter(a => a != null));
        return block('Descriptives', `<span class="chip k-obs">OBS</span>${PROTO}`, table('Descriptive statistics', head, out, 2)
          + (o.box ? plotWrap(boxPlot(groups, lv, lab(v0)), `${LBL[v0]} by ${s.split[0] ? LBL[s.split[0]].toLowerCase() : 'all rows'}. Box: median and IQR; whiskers: 1.5 × IQR; dots: observations.`) : '')
          + (o.hist ? plotWrap(histPlot(groups.flat(), lab(v0)), `Distribution of ${LBL[v0]}`) : ''), 'Descriptive only. No inference.'); } },

    ttest: { title: 'Paired Samples T-Test', status: notQualified, method: 'scipy.stats.ttest_rel',
      slots: [{ k: 'out', label: 'Outcome', rule: '1 numeric', max: 1, ok: t => t === 'n' }, { k: 'within', label: 'Paired by (repeated factor)', rule: '1 ordinal', max: 1, ok: t => t === 'o' || t === 'c' }, { k: 'subj', label: 'Subject', rule: '1 id', max: 1, ok: t => t === 'id' }],
      spec: { out: ['cmj_height'], within: ['occasion'], subj: ['athlete_id'] },
      sections: [{ t: 'Compare', items: [['sel:l1', 'Measure 1', 'Pre'], ['sel:l2', 'Measure 2', 'Post 24h']] }, { t: 'Additional statistics', items: [['md', 'Mean difference and 95% CI', 1], ['es', "Effect size (Cohen's d<sub>z</sub>)", 1], ['desc', 'Descriptives', 1]] }, { t: 'Plots', items: [['plot', 'Paired observations', 1]] }],
      syntax: (s, o) => `stats.<span class="k">ttest_rel</span>(wide[<span class="s">"${o.l2}"</span>], wide[<span class="s">"${o.l1}"</span>], nan_policy=<span class="s">"omit"</span>)`,
      run(s, o) { if (!s.out.length || !s.within.length || !s.subj.length) return empty('Assign an <b>Outcome</b>, the repeated factor in <b>Paired by</b>, and the <b>Subject</b>.');
        if (o.l1 === o.l2) return empty('Choose two different levels to compare.');
        const m = byLevel(s.out[0], s.within[0], s.subj[0]), pairs = Object.values(m).filter(x => x[o.l1] != null && x[o.l2] != null).map(x => [x[o.l1], x[o.l2]]), n = pairs.length;
        const d = pairs.map(([a, b]) => b - a), md = mean(d), sdd = sd(d), se = sdd / Math.sqrt(n), t = md / se, df = n - 1, p = pT(Math.abs(t), df), tc = tcrit(df);
        const head = ['Measure 1', 'Measure 2', 't', 'df', 'p'].concat(o.md ? ['Mean difference', 'SE', '95% CI'] : [], o.es ? ['d<sub>z</sub>'] : []);
        const r = [o.l1, o.l2, f(t), df, fp(p)].concat(o.md ? [`<b class="mod">${f(md)}</b>`, f(se), `${f(md - tc * se)} – ${f(md + tc * se)}`] : [], o.es ? [f(md / sdd)] : []);
        const dsc = o.desc ? table('Descriptives', ['Level', 'N', 'Mean', 'SD', 'SE'], [o.l1, o.l2].map((l, k) => { const v = pairs.map(pq => pq[k]); return [l, n, f(mean(v)), f(sd(v)), f(sd(v) / Math.sqrt(n))]; })) : '';
        return block('Paired Samples T-Test', `<span class="chip k-mod">MOD</span>${notQualified}${PROTO}`, `<div class="rsub">${lab(s.out[0])}: ${o.l2} − ${o.l1}, ${n} complete pairs</div>` + table('Paired samples test', head, [r], 2)
          + `<div class="tnote">Note. Student's paired t-test on complete pairs only (${n} of ${Object.keys(m).length} subjects). Two-sided.</div>` + dsc
          + (o.plot ? plotWrap(slopePlot(pairs, o.l1, o.l2, lab(s.out[0])), 'Each line is one athlete. Thick line: mean change (modeled). Red lines decreased.') : ''), 'Exploratory. Not a qualified method; promotion to evidence is disabled.'); } },

    anova: { title: 'Repeated Measures ANOVA', status: notQualified, method: 'statsmodels AnovaRM',
      slots: [{ k: 'out', label: 'Outcome', rule: '1 numeric', max: 1, ok: t => t === 'n' }, { k: 'within', label: 'Repeated measures factor', rule: '1 ordinal', max: 1, ok: t => t === 'o' || t === 'c' }, { k: 'subj', label: 'Subject', rule: '1 id', max: 1, ok: t => t === 'id' }],
      spec: { out: ['cmj_height'], within: ['occasion'], subj: ['athlete_id'] },
      sections: [{ t: 'Effect size', items: [['eta', 'Partial η²', 1]] }, { t: 'Assumption checks', items: [['sph', 'Sphericity (Mauchly)', 0, 'N/A in prototype']] }, { t: 'Post hoc', items: [['ph', 'Pairwise comparisons (Holm)', 1]] }, { t: 'Plots', items: [['plot', 'Means with 95% CI', 1]] }],
      syntax: s => `AnovaRM(data, depvar=<span class="s">"${s.out[0]}"</span>, subject=<span class="s">"${s.subj[0]}"</span>, within=[<span class="s">"${s.within[0]}"</span>]).<span class="k">fit</span>()`,
      run(s, o) { if (!s.out.length || !s.within.length || !s.subj.length) return empty('Assign an <b>Outcome</b>, the <b>Repeated measures factor</b> and the <b>Subject</b>.');
        const lv = levels(s.within[0]), m = byLevel(s.out[0], s.within[0], s.subj[0]), subj = Object.values(m).filter(x => lv.every(l => x[l] != null)), n = subj.length, k = lv.length;
        const G = mean(subj.flatMap(x => lv.map(l => x[l]))), mj = lv.map(l => mean(subj.map(x => x[l]))), mi = subj.map(x => mean(lv.map(l => x[l])));
        const ssC = n * mj.reduce((a, v) => a + (v - G) ** 2, 0), ssS = k * mi.reduce((a, v) => a + (v - G) ** 2, 0), ssT = subj.flatMap(x => lv.map(l => (x[l] - G) ** 2)).reduce((a, b) => a + b, 0), ssE = ssT - ssC - ssS;
        const d1 = k - 1, d2 = (k - 1) * (n - 1), F = (ssC / d1) / (ssE / d2), p = pF(F, d1, d2);
        const tab = table('Within subjects effects', ['Source', 'SS', 'df', 'Mean square', 'F', 'p'].concat(o.eta ? ['η²<sub>p</sub>'] : []), [[LBL[s.within[0]], f(ssC), d1, f(ssC / d1), `<b class="mod">${f(F)}</b>`, fp(p)].concat(o.eta ? [f(ssC / (ssC + ssE), 3)] : []), ['Residual', f(ssE), d2, f(ssE / d2), '', ''].concat(o.eta ? [''] : [])]);
        let ph = ''; if (o.ph) { const comps = []; for (let a = 0; a < k; a++) for (let b = a + 1; b < k; b++) { const dd = subj.map(x => x[lv[b]] - x[lv[a]]), t = mean(dd) / (sd(dd) / Math.sqrt(n)); comps.push({ a: lv[a], b: lv[b], md: mean(dd), t, p: pT(Math.abs(t), n - 1) }); }
          const ord = [...comps].sort((x, y) => x.p - y.p); let run = 0; ord.forEach((c, i) => { run = Math.max(run, Math.min(1, c.p * (comps.length - i))); c.ph = run; });
          ph = table('Post hoc comparisons', ['Comparison', 'Mean difference', 't', 'df', 'p<sub>Holm</sub>'], comps.map(c => [`${c.b} − ${c.a}`, f(c.md), f(c.t), n - 1, fp(c.ph)])); }
        const cis = lv.map(l => { const v = subj.map(x => x[l]); return tcrit(n - 1) * sd(v) / Math.sqrt(n); });
        return block('Repeated Measures ANOVA', `<span class="chip k-mod">MOD</span>${notQualified}${PROTO}`, `<div class="rsub">${lab(s.out[0])} across ${k} levels of ${LBL[s.within[0]].toLowerCase()}, ${n} complete subjects</div>` + tab
          + `<div class="tnote">Note. Complete cases only (${n} of ${Object.keys(m).length}). Sphericity not assessed in this prototype, so no Greenhouse–Geisser correction is shown. For unbalanced or missing data, prefer Mixed Models.</div>` + ph
          + (o.plot ? plotWrap(meansPlot(mj, cis, lv, lab(s.out[0])), 'Means with 95% CI (between-subject; does not remove athlete variability)') : ''), 'Exploratory. Not a qualified method; promotion to evidence is disabled.'); } },

    reg: { title: 'Linear Regression', status: notQualified, method: 'statsmodels OLS',
      slots: [{ k: 'dep', label: 'Dependent variable', rule: '1 numeric', max: 1, ok: t => t === 'n' }, { k: 'cov', label: 'Covariates', rule: 'numeric', ok: t => t === 'n' }],
      spec: { dep: ['cmj_height'], cov: ['sprint_20m'] },
      sections: [{ t: 'Model coefficients', items: [['ci', '95% confidence intervals', 1], ['std', 'Standardised estimates', 0]] }, { t: 'Model fit', items: [['fit', 'R², adjusted R², F test', 1]] }, { t: 'Plots', items: [['sc', 'Scatter with fit (one covariate)', 1], ['res', 'Residuals vs fitted', 0]] }],
      syntax: s => `smf.<span class="k">ols</span>(<span class="s">"${s.dep[0] || '?'} ~ ${s.cov.join(' + ') || '1'}"</span>, data).fit()`,
      run(s, o) { if (!s.dep.length || !s.cov.length) return empty('Assign a <b>Dependent variable</b> and at least one <b>Covariate</b>.');
        const use = rows.filter(r => [s.dep[0], ...s.cov].every(k => val(r, k) != null)), n = use.length, p = s.cov.length + 1;
        if (n <= p + 1) return empty(`Only ${n} complete rows. Not enough to fit ${p} parameters.`);
        const X = use.map(r => [1, ...s.cov.map(k => val(r, k))]), y = use.map(r => val(r, s.dep[0])), XtX = Array.from({ length: p }, (_, i) => Array.from({ length: p }, (_, j) => X.reduce((a, r) => a + r[i] * r[j], 0)));
        const XtXi = inv(XtX); if (!XtXi) return empty('The covariates are collinear. Remove one.');
        const Xty = Array.from({ length: p }, (_, i) => X.reduce((a, r, k) => a + r[i] * y[k], 0)), beta = XtXi.map(r => r.reduce((a, v, j) => a + v * Xty[j], 0));
        const fit = X.map(r => r.reduce((a, v, j) => a + v * beta[j], 0)), res = y.map((v, i) => v - fit[i]), rss = res.reduce((a, v) => a + v * v, 0), my = mean(y), tss = y.reduce((a, v) => a + (v - my) ** 2, 0);
        const s2 = rss / (n - p), se = XtXi.map((r, i) => Math.sqrt(s2 * r[i])), tc = tcrit(n - p), R2 = 1 - rss / tss, aR2 = 1 - (1 - R2) * (n - 1) / (n - p), Fv = ((tss - rss) / (p - 1)) / s2;
        const sdy = sd(y), names = ['Intercept', ...s.cov];
        const coef = table('Model coefficients', ['Term', 'Estimate', 'SE'].concat(o.ci ? ['95% CI'] : [], ['t', 'p'], o.std ? ['Std. estimate'] : []), beta.map((b, i) => [names[i], i ? `<b class="mod">${f(b, 3)}</b>` : f(b, 3), f(se[i], 3)].concat(o.ci ? [`${f(b - tc * se[i], 3)} – ${f(b + tc * se[i], 3)}`] : [], [f(b / se[i]), fp(pT(Math.abs(b / se[i]), n - p))], o.std ? [i ? f(b * sd(X.map(r => r[i])) / sdy, 3) : ''] : [])));
        const fitT = o.fit ? table('Model fit', ['N', 'R²', 'Adjusted R²', 'F', 'df', 'p'], [[n, f(R2, 3), f(aR2, 3), f(Fv), `${p - 1}, ${n - p}`, fp(pF(Fv, p - 1, n - p))]], 0) : '';
        const repeated = new Set(use.map(r => r.id)).size < n;
        const warn = repeated ? `<div class="note" style="margin-top:10px">These ${n} rows come from ${new Set(use.map(r => r.id)).size} athletes measured repeatedly, so the rows are not independent and these standard errors are too small. Use <b>Mixed Models</b> for repeated measures.</div>` : '';
        let plots = ''; if (o.sc && s.cov.length === 1) { const xv = X.map(r => r[1]), mx = mean(xv), sxx = xv.reduce((a, v) => a + (v - mx) ** 2, 0); plots += plotWrap(scatterFit(xv, y, beta[0], beta[1], g => tc * Math.sqrt(s2 * (1 / n + (g - mx) ** 2 / sxx)), lab(s.cov[0]), lab(s.dep[0])), 'Observed points; line and band: fitted mean ± 95% CI (modeled).'); }
        if (o.res) plots += plotWrap(residPlot(fit, res), 'Residuals vs fitted');
        return block('Linear Regression', `<span class="chip k-mod">MOD</span>${notQualified}${PROTO}`, `<div class="rsub mono" style="font-size:12px">${s.dep[0]} ~ ${s.cov.join(' + ')}</div>` + coef + fitT + warn + plots, 'Exploratory. Not a qualified method; promotion to evidence is disabled.'); } },

    freq: { title: 'Frequencies', status: '<span class="chip s-desc">DESCRIPTIVE</span>', method: 'pandas value_counts',
      slots: [{ k: 'vars', label: 'Variables', rule: 'categorical or id', ok: t => t !== 'n' }], spec: { vars: ['occasion'] },
      sections: [{ t: 'Plots', items: [['bar', 'Bar chart', 1]] }],
      syntax: s => s.vars.map(v => `data[<span class="s">"${v}"</span>].<span class="k">value_counts</span>()`).join('; ') || 'data.value_counts()',
      run(s, o) { if (!s.vars.length) return empty('Drag a categorical variable into <b>Variables</b>.');
        return s.vars.map(v => { const lv = levels(v), c = lv.map(l => rows.filter(r => val(r, v) === l).length), N = c.reduce((a, b) => a + b, 0); let cum = 0;
          const ok = lv.map(l => rows.filter(r => val(r, v) === l && r.h != null).length);
          return block(`Frequencies of ${LBL[v]}`, `<span class="chip k-obs">OBS</span>${PROTO}`, table('Counts', ['Level', 'Count', '%', 'Cumulative %', 'With CMJ height'], lv.map((l, i) => { cum += c[i]; return [l, c[i], f(c[i] / N * 100, 1), f(cum / N * 100, 1), ok[i] < c[i] ? `<span style="color:var(--bad)">${ok[i]} of ${c[i]}</span>` : ok[i]]; }))
            + (o.bar ? plotWrap(barPlot(lv.map(String), c), '') : '')); }).join(''); } },

    change: { title: 'Athlete Change', status: '<span class="chip k-obs">OBSERVED CHANGE</span>', method: 'pandas',
      slots: [{ k: 'out', label: 'Outcome', rule: '1 numeric', max: 1, ok: t => t === 'n' }, { k: 'within', label: 'Occasion factor', rule: '1 ordinal', max: 1, ok: t => t === 'o' }, { k: 'subj', label: 'Athlete', rule: '1 id', max: 1, ok: t => t === 'id' }],
      spec: { out: ['cmj_height'], within: ['occasion'], subj: ['athlete_id'] },
      sections: [{ t: 'Compare', items: [['sel:l1', 'From', 'Pre'], ['sel:l2', 'To', 'Post 24h']] }, { t: 'Threshold', items: [['num:thr', 'Smallest worthwhile change', '', 'cm']] }, { t: 'Display', items: [['sort', 'Sort by change', 1]] }],
      syntax: (s, o) => `wide[<span class="s">"${o.l2}"</span>] - wide[<span class="s">"${o.l1}"</span>]  <span class="c"># per ${s.subj[0] || 'athlete'}</span>`,
      run(s, o) { if (!s.out.length || !s.within.length || !s.subj.length) return empty('Assign the <b>Outcome</b>, the <b>Occasion factor</b> and the <b>Athlete</b>.');
        const m = byLevel(s.out[0], s.within[0], s.subj[0]); let items = Object.entries(m).filter(([, x]) => x[o.l1] != null && x[o.l2] != null).map(([id, x]) => ({ id, a: x[o.l1], b: x[o.l2], d: x[o.l2] - x[o.l1] }));
        const missing = Object.keys(m).length - items.length; if (o.sort) items = items.sort((p, q) => q.d - p.d);
        const thr = parseFloat(o.thr) || 0, up = items.filter(i => thr && i.d > thr).length, dn = items.filter(i => thr && i.d < -thr).length;
        const head = thr ? `<div class="note info" style="margin:6px 0 10px"><b>${up}</b> athletes above +${thr} ${UNIT[s.out[0]] || ''}, <b>${dn}</b> below −${thr}, ${items.length - up - dn} within. The threshold is your practitioner input, not a qualified noise band.</div>`
          : `<div class="note" style="margin:6px 0 10px">No qualified noise threshold exists for ${LBL[s.out[0]]}. Enter a smallest worthwhile change in the options to classify athletes.</div>`;
        return block(`Change in ${LBL[s.out[0]]}: ${o.l1} → ${o.l2}`, `<span class="chip k-obs">OBS</span>${thr ? '<span class="chip s-expl">PRACTITIONER THRESHOLD</span>' : ''}${PROTO}`, head + plotWrap(changeBars(items, thr), `${items.length} athletes${missing ? `, ${missing} missing a jump at one of the two occasions` : ''}. Mean change ${f(mean(items.map(i => i.d)))} ${UNIT[s.out[0]] || ''}.`)
          + table('Per athlete', ['Athlete', o.l1, o.l2, 'Change', 'Status'], items.map(i => [i.id, f(i.a, 1), f(i.b, 1), `<b>${(i.d > 0 ? '+' : '') + i.d.toFixed(1)}</b>`, !thr ? '<span class="faint">no threshold</span>' : Math.abs(i.d) <= thr ? 'within' : i.d > 0 ? '<span style="color:var(--ok)">↑ above</span>' : '<span style="color:var(--bad)">↓ below</span>'])), 'Observed change for practitioners. No inference.'); } },

    signals: { title: 'Signals', status: '<span class="chip s-qual">QUALIFIED</span>', method: 'SIGNAL', slots: [], spec: {}, sections: [],
      syntax: () => `<span class="k">signal</span>.derive(trace, rate_hz=<span class="s">1000</span>)  <span class="c"># SIGNAL (qualified)</span>`,
      run: () => `<div class="rblock"><div class="rtitle">Force-trace signal derivation <span class="chip s-qual">QUALIFIED</span></div><p class="muted" style="margin:8px 0 0">This works on raw force traces at 1000 Hz (MoveSmart). The Mendeley dataset holds derived summary values only, so there are no traces to process. The trace viewer and derivation screen are not drawn in this prototype.</p></div>` } };

  // ---------- state, options UI ----------
  const state = {}; let cur = null, picked = null;
  const st = an => state[an] || (state[an] = { spec: JSON.parse(JSON.stringify(DEF[an].spec)), opt: Object.fromEntries(DEF[an].sections.flatMap(sec => sec.items.map(([k, , d]) => [k.replace(/^(sel|num):/, ''), d]))) });
  const ico = t => `<span class="ico ${t}">${t === 'id' ? 'ID' : t.toUpperCase()}</span>`;
  const used = v => Object.values(st(cur).spec).some(a => a.includes(v));
  function renderOptions() {
    const D = DEF[cur], S2 = st(cur);
    $('#gtitle').textContent = D.title; $('#gstatus').innerHTML = D.status; $('#gmethod').textContent = D.method;
    const assign = D.slots.length ? `<div class="osec"><div class="b" style="padding-top:12px"><div class="assign"><div><div class="targets"><label>Variables <span class="rule">drag →</span></label></div><div class="vlist" id="gvlist">${Object.entries(VARS).map(([v, t]) => `<div class="v ${used(v) ? 'used' : ''} ${picked === v ? 'sel' : ''}" draggable="true" data-var="${v}" title="${LBL[v]} · ${S[t]}">${ico(t)}${v}</div>`).join('')}</div></div>
      <div class="targets">${D.slots.map(sl => `<div><label>${sl.label} <span class="rule">${sl.rule}</span></label><div class="tbox" data-gslot="${sl.k}">${S2.spec[sl.k].map(v => `<div class="tok" draggable="true" data-var="${v}">${ico(VARS[v])}${v}${UNIT[v] ? ` <span class="faint">${UNIT[v]}</span>` : ''}<span class="x" title="Remove">✕</span></div>`).join('')}</div></div>`).join('')}</div></div></div></div>` : '';
    const lvOpts = () => { const w = S2.spec.within && S2.spec.within[0]; return w ? levels(w) : OCC; };
    const secs = D.sections.map(sec => `<div class="osec"><div class="t"><span class="chev">▾</span>${sec.t}</div><div class="b">${sec.items.map(([k, label, d, extra]) => {
      if (k.startsWith('sel:')) { const kk = k.slice(4); return `<div class="sel-row" style="margin:3px 0"><span class="muted">${label}</span><select class="fsel" data-gsel="${kk}">${lvOpts().map(l => `<option ${String(S2.opt[kk]) === String(l) ? 'selected' : ''}>${l}</option>`).join('')}</select></div>`; }
      if (k.startsWith('num:')) { const kk = k.slice(4); return `<div class="sel-row" style="margin:3px 0"><span class="muted">${label}</span><span style="display:flex;gap:6px;align-items:center"><input class="fsel" data-gnum="${kk}" type="number" step="0.1" min="0" placeholder="not set" value="${S2.opt[kk] || ''}" style="width:100px"> <span class="faint">${extra || ''}</span></span></div>`; }
      const dis = typeof extra === 'string'; return `<div class="cb ${S2.opt[k] ? 'on' : ''} ${dis ? 'dis' : ''}" data-gopt="${k}" ${dis ? `title="${extra}"` : ''}><i>✓</i><span>${label}</span>${dis ? `<span class="hint chip s-unav">${extra}</span>` : ''}</div>`; }).join('')}</div></div>`).join('');
    $('#gopts').innerHTML = assign + secs;
  }
  function compute() { const D = DEF[cur], S2 = st(cur);
    $('#gresults').innerHTML = D.run(S2.spec, S2.opt);
    $('#syn').innerHTML = D.syntax(S2.spec, S2.opt) + (cur === 'signals' ? '' : `  <span class="c"># ${D.method}${['desc', 'freq', 'change'].includes(cur) ? '' : ' · not qualified'}</span>`);
    APP().buildOutline(); }
  const refresh = () => { renderOptions(); compute(); };
  const assignTo = (v, slot) => { const sl = DEF[cur].slots.find(x => x.k === slot), box = $(`[data-gslot="${slot}"]`);
    if (!sl.ok(VARS[v])) { box.classList.remove('reject'); void box.offsetWidth; box.classList.add('reject'); APP().toast(`${v} is ${S[VARS[v]]}. ${sl.label} needs ${sl.rule}.`); return; }
    const sp = st(cur).spec; Object.keys(sp).forEach(k => sp[k] = sp[k].filter(x => x !== v)); sl.max === 1 ? sp[slot] = [v] : sp[slot].push(v); picked = null; refresh(); };
  const opts = $('#gopts');
  opts.addEventListener('click', e => {
    const t = e.target;
    if (t.closest('.osec > .t')) { t.closest('.osec').classList.toggle('closed'); return; }
    const cb = t.closest('.cb[data-gopt]'); if (cb) { if (cb.classList.contains('dis')) { APP().toast(cb.title); return; } const k = cb.dataset.gopt; st(cur).opt[k] = !st(cur).opt[k]; refresh(); return; }
    if (t.classList.contains('x')) { const v = t.closest('.tok').dataset.var, slot = t.closest('[data-gslot]').dataset.gslot; st(cur).spec[slot] = st(cur).spec[slot].filter(x => x !== v); refresh(); return; }
    const v = t.closest('#gvlist .v'); if (v) { picked = picked === v.dataset.var ? null : v.dataset.var; renderOptions(); if (picked) APP().toast(`Click a box to assign ${picked}, or drag it`); return; }
    const box = t.closest('[data-gslot]'); if (box && picked) assignTo(picked, box.dataset.gslot);
  });
  opts.addEventListener('dblclick', e => { const v = e.target.closest('#gvlist .v'); if (!v) return; const sl = DEF[cur].slots.find(x => x.ok(VARS[v.dataset.var]) && (x.max !== 1 || !st(cur).spec[x.k].length)) || DEF[cur].slots.find(x => x.ok(VARS[v.dataset.var])); if (sl) assignTo(v.dataset.var, sl.k); else APP().toast(`${v.dataset.var} does not fit any box here`); });
  opts.addEventListener('change', e => { const s = e.target.dataset.gsel, n = e.target.dataset.gnum; if (s) { st(cur).opt[s] = e.target.value; compute(); } if (n) { st(cur).opt[n] = e.target.value; compute(); } });
  opts.addEventListener('input', e => { const n = e.target.dataset.gnum; if (n) { st(cur).opt[n] = e.target.value; compute(); } });
  opts.addEventListener('dragover', e => { const b = e.target.closest('[data-gslot]'); if (b) { e.preventDefault(); b.classList.add('over'); } });
  opts.addEventListener('dragleave', e => e.target.closest('[data-gslot]')?.classList.remove('over'));
  opts.addEventListener('drop', e => { const b = e.target.closest('[data-gslot]'), list = e.target.closest('#gvlist'); const v = e.dataTransfer.getData('text/plain');
    if (b) { e.preventDefault(); b.classList.remove('over'); assignTo(v, b.dataset.gslot); } else if (list) { e.preventDefault(); const sp = st(cur).spec; Object.keys(sp).forEach(k => sp[k] = sp[k].filter(x => x !== v)); refresh(); } });

  window.GEN = { show(an) { cur = an; picked = null; refresh(); $('#gresults').scrollTop = 0; } };
})();
