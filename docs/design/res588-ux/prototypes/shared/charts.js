/* Small dependency-free SVG chart renderers for the RES-588 design gate.
 * Aggregate values only. No network, no build step, no third-party runtime.
 */
window.RES588Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs = {}) {
    const el = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value !== null && value !== undefined) el.setAttribute(key, String(value));
    }
    return el;
  }

  function txt(parent, x, y, value, attrs = {}) {
    const node = svgEl("text", { x, y, ...attrs });
    node.textContent = value;
    parent.appendChild(node);
    return node;
  }

  function line(parent, x1, y1, x2, y2, attrs = {}) {
    parent.appendChild(svgEl("line", { x1, y1, x2, y2, ...attrs }));
  }

  function path(parent, d, attrs = {}) {
    parent.appendChild(svgEl("path", { d, ...attrs }));
  }

  const themes = {
    studio: {
      grid: "#222b2d", axis: "#3b4749", text: "#e9efed", muted: "#8d9a96",
      observed: "#e8b05c", observedSoft: "rgba(232,176,92,.14)", model: "#62c9b9",
      missing: "#e37a72", font: "'IBM Plex Sans', 'Segoe UI', sans-serif", mono: "'IBM Plex Mono', Consolas, monospace",
    },
    notebook: {
      grid: "#ded8c8", axis: "#8d8677", text: "#1d2420", muted: "#756f62",
      observed: "#2f5d50", observedSoft: "rgba(47,93,80,.10)", model: "#9b3d2e",
      missing: "#a44436", font: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif", mono: "'IBM Plex Mono', Consolas, monospace",
    },
    workspace: {
      grid: "#1c2732", axis: "#344351", text: "#dce8f1", muted: "#8394a5",
      observed: "#58c7d6", observedSoft: "rgba(88,199,214,.12)", model: "#a78bfa",
      missing: "#e08a83", font: "'Segoe UI Variable', 'Segoe UI', Inter, sans-serif", mono: "'Cascadia Code', 'IBM Plex Mono', Consolas, monospace",
    },
    atelier: {
      grid: "#ddd5c4", axis: "#9a8f7c", text: "#1f2a24", muted: "#706f63",
      observed: "#2f5d50", observedSoft: "rgba(47,93,80,.10)", model: "#9b4a32",
      missing: "#9e4034", font: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif", mono: "'IBM Plex Mono', Consolas, monospace",
    },
  };

  function observeResize(container, render) {
    let raf = null;
    const run = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => render());
    };
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(run);
      ro.observe(container);
    } else {
      window.addEventListener("resize", run);
    }
    if (document.fonts?.ready) document.fonts.ready.then(run);
    render();
  }

  function trajectory(container, options = {}) {
    const theme = themes[options.theme || "studio"];
    const { width = container.clientWidth, height = container.clientHeight } = options;
    const data = window.RES588.occasions;
    const model = window.RES588.model;
    const xDomain = [1, 4];
    const yDomain = [28, 52];
    const margin = { l: 54, r: 58, t: 20, b: 48 };
    const w = Math.max(320, width);
    const h = Math.max(220, height);
    const plotW = w - margin.l - margin.r;
    const plotH = h - margin.t - margin.b;
    const xs = (v) => margin.l + ((v - xDomain[0]) / (xDomain[1] - xDomain[0])) * plotW;
    const ys = (v) => margin.t + plotH - ((v - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH;
    const svg = svgEl("svg", {
      viewBox: `0 0 ${w} ${h}`,
      width: "100%",
      height: "100%",
      role: "img",
      "aria-label": "Occasion means with 95% confidence intervals and the MixedLM random-slope fit for countermovement jump height, 21 athletes, 82 observations.",
    });
    svg.style.display = "block";

    // Horizontal grid.
    for (let value = 30; value <= 50; value += 5) {
      line(svg, margin.l, ys(value), w - margin.r, ys(value), { stroke: theme.grid, "stroke-width": 1 });
      txt(svg, margin.l - 10, ys(value) + 4, String(value), {
        fill: theme.muted, "font-family": theme.mono, "font-size": 10.5, "text-anchor": "end",
      });
    }
    // Axis.
    line(svg, margin.l, margin.t, margin.l, h - margin.b, { stroke: theme.axis, "stroke-width": 1 });
    line(svg, margin.l, h - margin.b, w - margin.r, h - margin.b, { stroke: theme.axis, "stroke-width": 1 });
    txt(svg, 14, margin.t + plotH / 2, "CMJ height (cm)", {
      fill: theme.muted, "font-family": theme.mono, "font-size": 10.5, "text-anchor": "middle",
      transform: `rotate(-90 14 ${margin.t + plotH / 2})`,
    });

    // Observed mean confidence intervals.
    for (const point of data) {
      const x = xs(point.occasion);
      line(svg, x, ys(point.ciLow), x, ys(point.ciHigh), { stroke: theme.observed, "stroke-width": 1.4, opacity: 0.6 });
      line(svg, x - 5, ys(point.ciHigh), x + 5, ys(point.ciHigh), { stroke: theme.observed, "stroke-width": 1.4, opacity: 0.6 });
      line(svg, x - 5, ys(point.ciLow), x + 5, ys(point.ciLow), { stroke: theme.observed, "stroke-width": 1.4, opacity: 0.6 });
    }

    // Observed mean polyline.
    const points = data.map((point) => [xs(point.occasion), ys(point.mean)]);
    path(svg, points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" "), {
      fill: "none", stroke: theme.observed, "stroke-width": 2.2, "stroke-linejoin": "round", "stroke-linecap": "round",
    });

    // Model-implied fixed-effect line.
    const y1 = model.intercept;
    const y4 = model.intercept + model.slope * 3;
    line(svg, xs(1), ys(y1), xs(4), ys(y4), {
      stroke: theme.model, "stroke-width": 1.8, "stroke-dasharray": "7 5", "stroke-linecap": "round",
    });

    // Points and accessible titles.
    for (const point of data) {
      const circle = svgEl("circle", {
        cx: xs(point.occasion), cy: ys(point.mean), r: 4.6,
        fill: theme.observed, stroke: "#0c1012", "stroke-width": 1.4,
      });
      const title = svgEl("title");
      title.textContent = `Occasion ${point.occasion}: mean ${point.mean.toFixed(2)} cm, 95% CI ${point.ciLow.toFixed(2)}–${point.ciHigh.toFixed(2)}, n=${point.n}`;
      circle.appendChild(title);
      svg.appendChild(circle);
    }

    // Occasion labels and n.
    for (const point of data) {
      const x = xs(point.occasion);
      const anchor = point.occasion === 1 ? "start" : point.occasion === 4 ? "end" : "middle";
      txt(svg, x, h - 26, `Occasion ${point.occasion}`, {
        fill: theme.text, "font-family": theme.font, "font-size": 11, "text-anchor": anchor,
      });
      txt(svg, x, h - 10, `n=${point.n}${point.missing ? " · 2 missing" : ""}`, {
        fill: point.missing ? theme.missing : theme.muted,
        "font-family": theme.mono, "font-size": 9.5, "text-anchor": anchor,
      });
    }

    // Direct annotation for the model line.
    const labelX = xs(2.02);
    const labelY = ys(44.25);
    svg.appendChild(svgEl("rect", {
      x: labelX - 2, y: labelY - 13, width: 178, height: 20, rx: 2,
      fill: options.annotationBackground || "rgba(12,16,18,.72)",
    }));
    txt(svg, labelX + 4, labelY + 1, "MixedLM fit  +0.998 cm / occasion", {
      fill: theme.model, "font-family": theme.mono, "font-size": 9.8,
    });

    container.replaceChildren(svg);
  }

  function forest(container, options = {}) {
    const theme = themes[options.theme || "studio"];
    const model = window.RES588.model;
    const width = Math.max(220, options.width || container.clientWidth || 300);
    const height = Math.max(70, options.height || 88);
    const margin = { l: 8, r: 10, t: 24, b: 22 };
    const domain = [0, 4.6];
    const xs = (v) => margin.l + ((v - domain[0]) / (domain[1] - domain[0])) * (width - margin.l - margin.r);
    const svg = svgEl("svg", {
      viewBox: `0 0 ${width} ${height}`, width: "100%", height: "100%", role: "img",
      "aria-label": "Forest plot: change from occasion 1 to 4 is 2.995 centimetres, 95% confidence interval 1.866 to 4.124.",
    });
    const y = margin.t + 6;
    for (let value = 0; value <= 4; value += 1) {
      line(svg, xs(value), y - 6, xs(value), y + 12, { stroke: theme.grid, "stroke-width": 1 });
      txt(svg, xs(value), height - 6, String(value), {
        fill: theme.muted, "font-family": theme.mono, "font-size": 9, "text-anchor": "middle",
      });
    }
    line(svg, xs(0), y - 9, xs(0), y + 15, { stroke: theme.axis, "stroke-width": 1.2 });
    line(svg, xs(model.changeCi[0]), y, xs(model.changeCi[1]), y, { stroke: theme.observed, "stroke-width": 2.4, "stroke-linecap": "round" });
    line(svg, xs(model.changeCi[0]), y - 5, xs(model.changeCi[0]), y + 5, { stroke: theme.observed, "stroke-width": 1.4 });
    line(svg, xs(model.changeCi[1]), y - 5, xs(model.changeCi[1]), y + 5, { stroke: theme.observed, "stroke-width": 1.4 });
    svg.appendChild(svgEl("circle", { cx: xs(model.change), cy: y, r: 4.4, fill: theme.observed, stroke: options.pointStroke || "#0c1012", "stroke-width": 1.4 }));
    txt(svg, xs(model.change), y - 11, "+2.995", {
      fill: theme.text, "font-family": theme.mono, "font-size": 9.5, "text-anchor": "middle",
    });
    txt(svg, margin.l, height - 20, "Change 1 → 4 (cm)", {
      fill: theme.muted, "font-family": theme.mono, "font-size": 9,
    });
    container.replaceChildren(svg);
  }

  function monitoring(container, options = {}) {
    const theme = themes[options.theme || "workspace"];
    const width = Math.max(420, options.width || container.clientWidth || 700);
    const height = Math.max(220, options.height || 280);
    const margin = { l: 118, r: 24, t: 22, b: 42 };
    const plotW = width - margin.l - margin.r;
    const weeks = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    const xs = (week) => margin.l + ((week - 1) / 11) * plotW;
    const svg = svgEl("svg", {
      viewBox: `0 0 ${width} ${height}`, width: "100%", height: "100%", role: "img",
      "aria-label": "Monitoring timeline: eight planned weekly measurements in weeks 5 to 12, with four historical deposited readings kept on a separate occasion lane.",
    });

    txt(svg, margin.l, 13, "PLANNED SCHEDULE", { fill: theme.muted, "font-family": theme.mono, "font-size": 9.5, "letter-spacing": ".08em" });
    const plannedY = 46;
    for (const week of weeks) {
      line(svg, xs(week), 28, xs(week), height - margin.b, { stroke: theme.grid, "stroke-width": 1 });
      txt(svg, xs(week), height - 22, `W${week}`, { fill: theme.muted, "font-family": theme.mono, "font-size": 9, "text-anchor": "middle" });
    }
    line(svg, xs(5), plannedY, xs(12), plannedY, { stroke: theme.observed, "stroke-width": 1.4, "stroke-dasharray": "4 4", opacity: 0.55 });
    for (let week = 5; week <= 12; week += 1) {
      const g = svgEl("g");
      g.appendChild(svgEl("circle", { cx: xs(week), cy: plannedY, r: 7, fill: "none", stroke: theme.observed, "stroke-width": 1.6 }));
      const title = svgEl("title");
      title.textContent = `Week ${week}: planned measurement, no reading`;
      g.appendChild(title);
      svg.appendChild(g);
    }
    txt(svg, 12, plannedY + 4, "Weeks 5–12", { fill: theme.text, "font-family": theme.font, "font-size": 11 });
    txt(svg, 12, plannedY + 18, "8 planned", { fill: theme.muted, "font-family": theme.mono, "font-size": 9 });
    txt(svg, xs(5.2), plannedY - 16, "planned ≠ observed reading", { fill: theme.observed, "font-family": theme.mono, "font-size": 9 });

    // Separate historical lane.
    const baseY = height - margin.b;
    line(svg, margin.l, baseY - 4, width - margin.r, baseY - 4, { stroke: theme.axis, "stroke-width": 1 });
    const histY = plannedY + 98;
    txt(svg, margin.l, histY - 30, "DEPOSITED READINGS · OCCASION SCALE", { fill: theme.muted, "font-family": theme.mono, "font-size": 9.5, "letter-spacing": ".08em" });
    txt(svg, 12, histY + 4, "Occasions 1–4", { fill: theme.text, "font-family": theme.font, "font-size": 11 });
    txt(svg, 12, histY + 18, "historical", { fill: theme.muted, "font-family": theme.mono, "font-size": 9 });
    const hx = (index) => margin.l + 24 + index * 92;
    line(svg, hx(0), histY, hx(3), histY, { stroke: theme.model, "stroke-width": 2, "stroke-linecap": "round" });
    for (let i = 0; i < 4; i += 1) {
      const point = window.RES588.occasions[i];
      const g = svgEl("g");
      g.appendChild(svgEl("rect", { x: hx(i) - 5, y: histY - 5, width: 10, height: 10, rx: 1.5, fill: theme.model }));
      const title = svgEl("title");
      title.textContent = `Historical occasion ${point.occasion}: mean ${point.mean.toFixed(2)} cm, n=${point.n}; not mapped to a monitoring week`;
      g.appendChild(title);
      svg.appendChild(g);
      txt(svg, hx(i), histY + 23, `O${point.occasion}`, { fill: theme.muted, "font-family": theme.mono, "font-size": 9, "text-anchor": "middle" });
      txt(svg, hx(i), histY + 35, `${point.mean.toFixed(1)} cm`, { fill: theme.text, "font-family": theme.mono, "font-size": 8.5, "text-anchor": "middle" });
    }
    txt(svg, hx(3) + 22, histY + 4, "not weeks", { fill: theme.missing, "font-family": theme.mono, "font-size": 8.5 });
    container.replaceChildren(svg);
  }

  return { trajectory, forest, monitoring, themes, observeResize };
})();
