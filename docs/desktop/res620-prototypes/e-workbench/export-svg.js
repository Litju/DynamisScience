// RES-620: exports the current E screen as a true vector SVG (rects, borders, text, inline SVG plots).
// Active only with "svgexport" in the URL hash; the result replaces the page in <textarea id="svgout">.
// shortcut: CSS gradients/hatches and blur filters are dropped; the 3D canvas is embedded as an image.
(() => {
  if (!location.hash.includes('svgexport')) return;
  const W = innerWidth, H = innerHeight, esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const col = c => { if (!c) return null; let m = c.match(/rgba?\(([^)]+)\)/), p, a;
    if (m) { p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); a = p.length > 3 ? p[3] : 1; }
    else if ((m = c.match(/color\(srgb ([^)]+)\)/))) { const q = m[1].split(/[ /]+/).filter(Boolean).map(Number); p = q.slice(0, 3).map(v => Math.round(v * 255)); a = q.length > 3 ? q[3] : 1; }
    else return null;
    return a === 0 ? null : { c: `rgb(${p[0]},${p[1]},${p[2]})`, a }; };
  const paint = (attr, c) => { const v = col(c); return v ? ` ${attr}="${v.c}"${v.a < 1 ? ` ${attr}-opacity="${+v.a.toFixed(3)}"` : ''}` : ` ${attr}="none"`; };
  const px = v => parseFloat(v) || 0;
  let clipN = 0; const defs = [];
  const visible = (r, c) => r.right > c.l && r.left < c.r && r.bottom > c.t && r.top < c.b;

  function box(el, cs, r) {
    let s = ''; const rad = Math.min(px(cs.borderTopLeftRadius), r.height / 2, r.width / 2);
    const bg = col(cs.backgroundColor), sh = cs.boxShadow && cs.boxShadow !== 'none' && !cs.boxShadow.startsWith('inset');
    if (bg) s += `<rect x="${r.left}" y="${r.top}" width="${r.width}" height="${r.height}" rx="${rad}"${paint('fill', cs.backgroundColor)}${sh ? ' filter="url(#ds)"' : ''}/>`;
    const sides = ['Top', 'Right', 'Bottom', 'Left'].map(k => ({ w: px(cs[`border${k}Width`]), c: cs[`border${k}Color`], st: cs[`border${k}Style`] }));
    const dash = st => st === 'dashed' ? ' stroke-dasharray="4 3"' : st === 'dotted' ? ' stroke-dasharray="1.5 2"' : '';
    if (sides.every(b => b.w === sides[0].w && b.c === sides[0].c && b.st === sides[0].st) && sides[0].w > 0 && sides[0].st !== 'none' && col(sides[0].c)) {
      const w = sides[0].w; s += `<rect x="${r.left + w / 2}" y="${r.top + w / 2}" width="${Math.max(0, r.width - w)}" height="${Math.max(0, r.height - w)}" rx="${Math.max(0, rad - w / 2)}" fill="none"${paint('stroke', sides[0].c)} stroke-width="${w}"${dash(sides[0].st)}/>`;
    } else sides.forEach((b, i) => { if (!b.w || b.st === 'none' || !col(b.c)) return; const o = b.w / 2;
      const [x1, y1, x2, y2] = [[r.left, r.top + o, r.right, r.top + o], [r.right - o, r.top, r.right - o, r.bottom], [r.left, r.bottom - o, r.right, r.bottom - o], [r.left + o, r.top, r.left + o, r.bottom]][i];
      s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"${paint('stroke', b.c)} stroke-width="${b.w}"${dash(b.st)}/>`; });
    // inset box-shadow used as an underline/accent bar
    const ins = cs.boxShadow && cs.boxShadow.match(/(rgba?\([^)]+\)) 0px (-?\d+)px 0px 0px inset/);
    if (ins) { const h = Math.abs(+ins[2]); s += `<rect x="${r.left}" y="${+ins[2] < 0 ? r.bottom - h : r.top}" width="${r.width}" height="${h}"${paint('fill', ins[1])}/>`; }
    return s;
  }
  function textRun(x, y, s, cs) {
    if (cs.textTransform === 'uppercase') s = s.toUpperCase();
    const deco = cs.textDecorationLine && cs.textDecorationLine.includes('line-through') ? ' text-decoration="line-through"' : '';
    const ls = px(cs.letterSpacing) ? ` letter-spacing="${px(cs.letterSpacing)}"` : '';
    return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-family="${esc(cs.fontFamily)}" font-size="${cs.fontSize}" font-weight="${cs.fontWeight}"${cs.fontStyle === 'italic' ? ' font-style="italic"' : ''}${paint('fill', cs.color)}${deco}${ls} xml:space="preserve">${esc(s)}</text>`;
  }
  function textNode(node, clip) {
    const t = node.textContent; if (!t.trim()) return '';
    const cs = getComputedStyle(node.parentElement), rg = document.createRange(), lines = []; let cur = null;
    for (let i = 0; i < t.length; i++) { rg.setStart(node, i); rg.setEnd(node, i + 1); const rr = rg.getClientRects()[0]; if (!rr || !rr.width && /\s/.test(t[i])) continue;
      if (!cur || Math.abs(rr.top - cur.top) > 2) { if (/\s/.test(t[i])) continue; cur = { top: rr.top, left: rr.left, h: rr.height, right: rr.right, s: '' }; lines.push(cur); }
      cur.s += t[i]; cur.right = rr.right; }
    return lines.filter(l => visible({ left: l.left, right: l.right, top: l.top, bottom: l.top + l.h }, clip))
      .map(l => textRun(l.left, l.top + l.h * 0.76, l.s.replace(/\s+/g, ' ').trimEnd(), cs)).join('');
  }
  function pseudo(el, which, r) {
    const ps = getComputedStyle(el, which), c = ps.content; if (!c || c === 'none' || c === 'normal' || !/^".*"$/.test(c)) return '';
    const s = JSON.parse(c); if (!s.trim()) return '';
    const cs = getComputedStyle(el), fs = px(ps.fontSize) || px(cs.fontSize), y = r.top + r.height / 2 + fs * 0.35;
    const x = which === '::before' ? r.left + px(cs.paddingLeft) + px(ps.paddingLeft) : r.right - px(cs.paddingRight) - fs * 0.7 * s.length;
    return textRun(x, y, s, ps);
  }
  function svgClone(svg, r) {
    const c = svg.cloneNode(true), src = [svg, ...svg.querySelectorAll('*')], dst = [c, ...c.querySelectorAll('*')];
    src.forEach((s, i) => { const d = dst[i], k = getComputedStyle(s);
      if (/^(path|line|polyline|polygon|rect|circle|ellipse|text|tspan)$/.test(s.tagName)) {
        const f = k.fill.startsWith('url') ? null : k.fill, st = k.stroke;
        if (f !== null) d.setAttribute('fill', col(f) ? col(f).c : 'none'); if (col(f) && col(f).a < 1) d.setAttribute('fill-opacity', col(f).a);
        d.setAttribute('stroke', col(st) ? col(st).c : 'none'); if (col(st) && col(st).a < 1) d.setAttribute('stroke-opacity', col(st).a);
        if (k.strokeWidth) d.setAttribute('stroke-width', k.strokeWidth); if (k.strokeDasharray && k.strokeDasharray !== 'none') d.setAttribute('stroke-dasharray', k.strokeDasharray);
        if (k.opacity !== '1') d.setAttribute('opacity', k.opacity);
        if (s.tagName === 'text') { d.setAttribute('font-family', k.fontFamily); d.setAttribute('font-size', k.fontSize); d.setAttribute('font-weight', k.fontWeight); }
      }
      d.removeAttribute('style'); d.removeAttribute('class'); });
    if (!c.getAttribute('viewBox')) c.setAttribute('viewBox', `0 0 ${r.width} ${r.height}`);
    Object.entries({ x: r.left, y: r.top, width: r.width, height: r.height }).forEach(([k, v]) => c.setAttribute(k, v));
    return new XMLSerializer().serializeToString(c);
  }
  function walk(el, clip) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0 || /^(SCRIPT|STYLE|TEMPLATE|LINK|META|TITLE)$/.test(el.tagName)) return '';
    const r = el.getBoundingClientRect(); if (r.width && r.height && !visible(r, clip)) return '';
    let s = '', close = '';
    const op = +cs.opacity; if (op < 1) { s += `<g opacity="${op}">`; close = '</g>'; }
    if (el.tagName === 'svg') return s + svgClone(el, r) + close;
    if (el.tagName === 'CANVAS') return s + `<image x="${r.left}" y="${r.top}" width="${r.width}" height="${r.height}" href="${el.toDataURL()}"/>` + close;
    s += box(el, cs, r);
    if (el.tagName === 'SELECT') s += textRun(r.left + px(cs.paddingLeft) + 1, r.top + r.height / 2 + px(cs.fontSize) * .35, el.options[el.selectedIndex]?.text || '', cs) + textRun(r.right - 18, r.top + r.height / 2 + 4, '⌄', cs);
    if (el.tagName === 'INPUT') { const v = el.value || el.placeholder; if (v) { const pc = el.value ? cs : getComputedStyle(el, '::placeholder'); s += textRun(r.left + px(cs.paddingLeft), r.top + r.height / 2 + px(cs.fontSize) * .35, v, el.value ? cs : { color: pc.color, fontFamily: cs.fontFamily, fontSize: cs.fontSize, fontWeight: cs.fontWeight, fontStyle: cs.fontStyle, letterSpacing: cs.letterSpacing, textTransform: 'none', textDecorationLine: 'none' }); } }
    s += pseudo(el, '::before', r);
    let inner = clip, g = '';
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
      const id = 'c' + clipN++, rad = Math.min(px(cs.borderTopLeftRadius), r.height / 2);
      defs.push(`<clipPath id="${id}"><rect x="${r.left}" y="${r.top}" width="${r.width}" height="${r.height}" rx="${rad}"/></clipPath>`);
      g = `<g clip-path="url(#${id})">`; inner = { l: Math.max(clip.l, r.left), t: Math.max(clip.t, r.top), r: Math.min(clip.r, r.right), b: Math.min(clip.b, r.bottom) };
    }
    let kids = '';
    for (const n of el.childNodes) kids += n.nodeType === 3 ? textNode(n, inner) : n.nodeType === 1 ? walk(n, inner) : '';
    s += g ? g + kids + '</g>' : kids;
    s += pseudo(el, '::after', r);
    return s + close;
  }
  addEventListener('load', () => setTimeout(() => {
    const bg = getComputedStyle(document.body).backgroundColor;
    const body = walk(document.body, { l: 0, t: 0, r: W, b: H });
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`
      + `<defs><filter id="ds" x="-5%" y="-5%" width="110%" height="120%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity=".10"/></filter>${defs.join('')}</defs>`
      + `<rect width="${W}" height="${H}"${paint('fill', bg)}/>${body}</svg>`;
    document.body.innerHTML = ''; const ta = document.createElement('textarea'); ta.id = 'svgout'; ta.textContent = svg; document.body.appendChild(ta);
  }, 1500));
})();
