// RES-620 prototype helpers: illustrative SVG plots and screen switching. Values plotted are illustrative shapes.
const P = (() => {
  let seed = 20261110;
  const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const C = { line: '#D8D2C7', grid: '#EEEAE3', dim: '#6D7178', obs: '#2B2E33', mod: '#2F59B0', hyp: '#B7791F' };
  const occasions = ['Pre', 'Post 0', 'Post 10m', 'Post 24h'];
  // illustrative CMJ heights: 21 athletes × 4 occasions with athlete intercepts, slope ≈ 1 cm/occasion
  const athletes = Array.from({ length: 21 }, () => 33 + gauss() * 4);
  const obs = athletes.flatMap((a, i) => occasions.map((_, o) => ({ a: i, o, y: a + o * 0.998 + gauss() * 1.2 })));

  function frame(w, h, xl, yl, x0, x1, yr, opts = {}) {
    const xr = [x0, x1];
    const m = { l: 44, r: 12, t: 12, b: 34 };
    const sx = x => m.l + (x - xr[0]) / (xr[1] - xr[0]) * (w - m.l - m.r);
    const sy = y => h - m.b - (y - yr[0]) / (yr[1] - yr[0]) * (h - m.t - m.b);
    let s = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI" font-size="10">`;
    s += `<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#B7791F10"/><line x1="0" y1="0" x2="0" y2="6" stroke="#B7791F66" stroke-width="2"/></pattern></defs>`;
    const yt = opts.yticks || 5;
    for (let i = 0; i <= yt; i++) {
      const v = yr[0] + (yr[1] - yr[0]) * i / yt, y = sy(v);
      s += `<line x1="${m.l}" x2="${w - m.r}" y1="${y}" y2="${y}" stroke="${C.grid}"/><text x="${m.l - 6}" y="${y + 3}" fill="${C.dim}" text-anchor="end">${(Math.round(v) || 0).toFixed(0)}</text>`;
    }
    s += `<line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${h - m.b}" stroke="${C.line}"/><line x1="${m.l}" x2="${w - m.r}" y1="${h - m.b}" y2="${h - m.b}" stroke="${C.line}"/>`;
    s += `<text x="${(w + m.l) / 2}" y="${h - 4}" fill="${C.dim}" text-anchor="middle">${xl}</text>`;
    s += `<text transform="translate(11 ${(h - m.b) / 2 + 6}) rotate(-90)" fill="${C.dim}" text-anchor="middle">${yl}</text>`;
    return { s, sx, sy, m, w, h };
  }

  function trend(opts = {}) {
    const f = frame(opts.w || 520, opts.h || 260, 'Occasion', 'CMJ height (cm)', 0, 1, [24, 44], {});
    const x = o => f.sx(0.08 + o * 0.28);
    occasions.forEach((n, o) => f.s += `<text x="${x(o)}" y="${f.h - f.m.b + 13}" fill="${C.dim}" text-anchor="middle">${n}</text>`);
    if (opts.spaghetti) athletes.forEach((_, i) => {
      const pts = obs.filter(p => p.a === i).map(p => `${x(p.o)},${f.sy(p.y)}`).join(' ');
      f.s += `<polyline points="${pts}" fill="none" stroke="#2B2E3322"/>`;
    });
    obs.forEach(p => f.s += `<circle cx="${x(p.o) + (p.a - 10) * 0.9}" cy="${f.sy(p.y)}" r="2.2" fill="${C.obs}" opacity=".75"/>`);
    const mean = o => 33 + o * 0.998, hw = o => 1.4 + Math.abs(o - 1.5) * 0.25;
    const band = occasions.map((_, o) => `${x(o)},${f.sy(mean(o) + hw(o))}`).concat(occasions.map((_, o) => `${x(3 - o)},${f.sy(mean(3 - o) - hw(3 - o))}`)).join(' ');
    f.s += `<polygon points="${band}" fill="#2F59B022" stroke="none"/>`;
    f.s += `<polyline points="${occasions.map((_, o) => `${x(o)},${f.sy(mean(o))}`).join(' ')}" fill="none" stroke="${C.mod}" stroke-width="2"/>`;
    if (opts.scenario) {
      const sm = o => 33 + o * 0.998 + (o > 1 ? (o - 1) * 1.6 : 0);
      const sb = [1, 2, 3].map(o => `${x(o)},${f.sy(sm(o) + 2.2)}`).concat([3, 2, 1].map(o => `${x(o)},${f.sy(sm(o) - 2.2)}`)).join(' ');
      f.s += `<polygon points="${sb}" fill="url(#hatch)" stroke="#B7791F88" stroke-dasharray="4 3"/>`;
      f.s += `<polyline points="${[1, 2, 3].map(o => `${x(o)},${f.sy(sm(o))}`).join(' ')}" fill="none" stroke="${C.hyp}" stroke-width="2" stroke-dasharray="6 4"/>`;
      f.s += `<text x="${x(3) - 4}" y="${f.sy(sm(3) + 2.8)}" fill="${C.hyp}" text-anchor="end" font-family="Consolas" font-size="9">HYPOTHETICAL · not observed</text>`;
    }
    return f.s + '</svg>';
  }

  function qq(opts = {}) {
    const n = 82, r = Array.from({ length: n }, () => gauss() * 0.95 + (rnd() < .05 ? 1.4 : 0)).sort((a, b) => a - b);
    const q = i => { const p = (i + 0.5) / n; const t = Math.sqrt(-2 * Math.log(p < .5 ? p : 1 - p)); const z = t - (2.515517 + .802853 * t + .010328 * t * t) / (1 + 1.432788 * t + .189269 * t * t + .001308 * t ** 3); return p < .5 ? -z : z; };
    const f = frame(opts.w || 300, opts.h || 230, 'Theoretical normal quantile', 'Marginal resid. / cond. SD', -3, 3, [-3, 3], { yticks: 6 });
    f.s += `<line x1="${f.sx(-2.5)}" y1="${f.sy(-2.5)}" x2="${f.sx(2.5)}" y2="${f.sy(2.5)}" stroke="#6D717855" stroke-dasharray="3 3"/>`;
    r.forEach((v, i) => f.s += `<circle cx="${f.sx(q(i))}" cy="${f.sy(v)}" r="2.2" fill="none" stroke="${C.mod}"/>`);
    return f.s + '</svg>';
  }

  function residFitted(opts = {}) {
    const f = frame(opts.w || 300, opts.h || 230, 'Fitted (cm)', 'Conditional Pearson resid.', 26, 44, [-3, 3], { yticks: 6 });
    f.s += `<line x1="${f.sx(26)}" x2="${f.sx(44)}" y1="${f.sy(0)}" y2="${f.sy(0)}" stroke="#6D717866"/>`;
    obs.forEach(p => f.s += `<circle cx="${f.sx(Math.min(43.5, Math.max(26.5, p.y + gauss() * .6)))}" cy="${f.sy(gauss() * .9)}" r="2" fill="${C.mod}" opacity=".7"/>`);
    return f.s + '</svg>';
  }

  function ranef(opts = {}) {
    const f = frame(opts.w || 300, opts.h || 230, 'Athlete random intercept (cm)', 'Count', -10, 10, [0, 8], { yticks: 4 });
    const bins = Array(10).fill(0); athletes.forEach(a => { const b = Math.min(9, Math.max(0, Math.floor((a - 33 + 10) / 2))); bins[b]++; });
    bins.forEach((c, i) => f.s += `<rect x="${f.sx(-10 + i * 2) + 1}" y="${f.sy(c)}" width="${f.sx(-8) - f.sx(-10) - 2}" height="${f.sy(0) - f.sy(c)}" fill="#2F59B044" stroke="${C.mod}"/>`);
    return f.s + '</svg>';
  }

  function icc(opts = {}) {
    // illustrative: trial-to-trial peak Fz per participant, MoveSmart walking
    const f = frame(opts.w || 300, opts.h || 230, 'Participant', 'Peak Fz (N)', 0.5, 10.5, [600, 1400], {});
    for (let p = 1; p <= 10; p++) { const base = 820 + rnd() * 420; for (let t = 0; t < 8; t++) f.s += `<circle cx="${f.sx(p + (t - 3.5) * .05)}" cy="${f.sy(base + gauss() * 70)}" r="2" fill="${C.obs}" opacity=".8"/>`; f.s += `<text x="${f.sx(p)}" y="${f.h - f.m.b + 13}" fill="${C.dim}" text-anchor="middle">P${p}</text>`; }
    return f.s + '</svg>';
  }

  function changeVsMdc(opts = {}) {
    // practitioner view: athlete change vs ±MDC95 band (210 N), illustrative
    const names = ['A01', 'A02', 'A03', 'A04', 'A05', 'A06', 'A07', 'A08', 'A09', 'A10'];
    const f = frame(opts.w || 520, opts.h || 220, 'Athlete', 'Δ peak Fz vs baseline (N)', 0.5, 10.5, [-400, 400], {});
    f.s += `<rect x="${f.sx(.5)}" y="${f.sy(210)}" width="${f.sx(10.5) - f.sx(.5)}" height="${f.sy(-210) - f.sy(210)}" fill="#2F59B012" stroke="#2F59B055" stroke-dasharray="4 3"/>`;
    f.s += `<text x="${f.sx(10.4)}" y="${f.sy(210) - 4}" fill="${C.mod}" text-anchor="end" font-family="Consolas" font-size="9">±MDC95 210 N (modeled)</text>`;
    names.forEach((n, i) => { const d = gauss() * 170; const out = Math.abs(d) > 210; f.s += `<line x1="${f.sx(i + 1)}" x2="${f.sx(i + 1)}" y1="${f.sy(0)}" y2="${f.sy(d)}" stroke="${out ? '#2B2E33' : '#6D7178'}" stroke-width="3"/><circle cx="${f.sx(i + 1)}" cy="${f.sy(d)}" r="3.5" fill="${out ? '#2B2E33' : '#6D7178'}"/><text x="${f.sx(i + 1)}" y="${f.h - f.m.b + 13}" fill="${C.dim}" text-anchor="middle">${n}</text>`; });
    return f.s + '</svg>';
  }

  function mount() {
    document.querySelectorAll('[data-plot]').forEach(el => {
      const [name, ...flags] = el.dataset.plot.split(' ');
      const o = {}; flags.forEach(k => o[k] = true);
      el.innerHTML = ({ trend, qq, residFitted, ranef, icc, changeVsMdc })[name](o);
    });
    document.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', () => go(b.dataset.go, b.dataset.group || 'main')));
    // deep link for renders: #screenA,screenB opens those screens in their groups
    location.hash.slice(1).split(',').filter(Boolean).forEach(id => { const el = document.getElementById(id); if (el) go(id, el.dataset.screenGroup); });
  }
  function go(id, group = 'main') {
    document.querySelectorAll(`[data-screen-group="${group}"]`).forEach(s => s.classList.toggle('on', s.id === id));
    document.querySelectorAll('[data-go]').forEach(b => { if ((b.dataset.group || 'main') === group) b.classList.toggle('on', b.dataset.go === id); });
  }
  return { mount, go };
})();
document.addEventListener('DOMContentLoaded', P.mount);
