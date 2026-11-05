(function () {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}) => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
    return node;
  };
  const txt = (parent, x, y, value, attrs = {}) => {
    const node = el("text", { x, y, ...attrs });
    node.textContent = value;
    parent.appendChild(node);
    return node;
  };
  const line = (parent, x1, y1, x2, y2, attrs = {}) => parent.appendChild(el("line", { x1, y1, x2, y2, ...attrs }));
  const path = (parent, d, attrs = {}) => parent.appendChild(el("path", { d, ...attrs }));

  const toast = document.getElementById("toast");
  let timer;
  document.querySelectorAll("[data-toast]").forEach((node) => {
    node.addEventListener("click", () => {
      if (!toast) return;
      toast.textContent = node.dataset.toast;
      toast.classList.add("show");
      clearTimeout(timer);
      timer = setTimeout(() => toast.classList.remove("show"), 3200);
    });
  });

  function renderLoad(container) {
    const data = window.PERF.weekly;
    const width = Math.max(320, container.clientWidth);
    const height = Math.max(150, container.clientHeight);
    const margin = { l: 36, r: 12, t: 10, b: 22 };
    const plotW = width - margin.l - margin.r;
    const plotH = height - margin.t - margin.b;
    const xs = (week) => margin.l + ((week - 1) / 15) * plotW;
    const ys = (value) => margin.t + plotH - ((value - 150) / 250) * plotH;
    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", height: "100%", role: "img", "aria-label": "Weekly team mean training impulse, weeks 1 to 16, with match weeks highlighted." });
    data.forEach((point, index) => {
      if (point.phase === "MATCH") {
        svg.appendChild(el("rect", { x: xs(point.week) - plotW / 30, y: margin.t, width: plotW / 15, height: plotH, fill: "rgba(224,164,88,.06)" }));
      }
    });
    [150, 200, 250, 300, 350, 400].forEach((value) => {
      line(svg, margin.l, ys(value), width - margin.r, ys(value), { stroke: "#22333e", "stroke-width": 1 });
      txt(svg, margin.l - 6, ys(value) + 3, String(value), { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 7.5, "text-anchor": "end" });
    });
    data.forEach((point, index) => {
      if (index % 2 === 0) txt(svg, xs(point.week), height - 7, `W${point.week}`, { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 6.5, "text-anchor": "middle" });
    });
    const points = data.map((p) => [xs(p.week), ys(p.ti)]);
    const area = `M${points[0][0]},${margin.t + plotH} ` + points.map((p) => `L${p[0]},${p[1]}`).join(" ") + ` L${points[points.length - 1][0]},${margin.t + plotH} Z`;
    svg.appendChild(el("path", { d: area, fill: "rgba(95,212,232,.08)" }));
    // 4-week moving average.
    const avg = data.map((p, i) => {
      const slice = data.slice(Math.max(0, i - 3), i + 1);
      return [xs(p.week), ys(slice.reduce((sum, q) => sum + q.ti, 0) / slice.length)];
    });
    path(svg, avg.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" "), { fill: "none", stroke: "#7f919d", "stroke-width": 1, "stroke-dasharray": "3 3" });
    path(svg, points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" "), { fill: "none", stroke: "#5fd4e8", "stroke-width": 1.8, "stroke-linejoin": "round" });
    points.forEach((p, i) => {
      const point = data[i];
      svg.appendChild(el("circle", { cx: p[0], cy: p[1], r: point.week === 16 ? 3.6 : 2.2, fill: point.week === 16 ? "#c8f36b" : "#5fd4e8", stroke: "#0a1016", "stroke-width": 1 }));
    });
    // Last value callout.
    txt(svg, xs(16) - 4, ys(data[15].ti) - 9, "264.7", { fill: "#c8f36b", "font-family": "'IBM Plex Mono',monospace", "font-size": 7.5, "text-anchor": "end" });
    container.replaceChildren(svg);
  }

  function renderForce(container) {
    const data = window.PERF.trace;
    const phases = window.PERF.phases;
    const width = Math.max(320, container.clientWidth);
    const height = Math.max(160, container.clientHeight);
    const margin = { l: 38, r: 8, t: 10, b: 20 };
    const plotW = width - margin.l - margin.r;
    const plotH = height - margin.t - margin.b;
    const tMax = 2.35;
    const fMin = 200;
    const fMax = 1700;
    const xs = (t) => margin.l + (t / tMax) * plotW;
    const ys = (f) => margin.t + plotH - ((f - fMin) / (fMax - fMin)) * plotH;
    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", height: "100%", role: "img", "aria-label": "Vertical ground reaction force over time for a countermovement jump, with quiet standing, unweighting, braking, propulsion, flight and landing phases." });
    const colors = { QUIET_STANDING: "rgba(127,145,157,.08)", UNWEIGHTING: "rgba(95,212,232,.08)", BRAKING: "rgba(224,164,88,.10)", PROPULSION: "rgba(200,243,107,.10)", FLIGHT: "rgba(167,139,250,.10)", LANDING: "rgba(239,107,99,.10)" };
    phases.forEach((p) => {
      svg.appendChild(el("rect", { x: xs(p.start), y: margin.t, width: Math.max(1, xs(p.end) - xs(p.start)), height: plotH, fill: colors[p.phase] || "transparent" }));
      txt(svg, xs(p.start) + 2, height - 5, p.phase.slice(0, 4), { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 5.8 });
    });
    [200, 600, 1000, 1400, 1800].forEach((value) => {
      line(svg, margin.l, ys(value), width - margin.r, ys(value), { stroke: "#22333e", "stroke-width": 1 });
      txt(svg, margin.l - 5, ys(value) + 3, String(value), { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 6.5, "text-anchor": "end" });
    });
    line(svg, margin.l, ys(window.PERF.trial.bodyWeight), width - margin.r, ys(window.PERF.trial.bodyWeight), { stroke: "#e0a458", "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0.7 });
    txt(svg, width - margin.r - 2, ys(window.PERF.trial.bodyWeight) - 3, "body weight", { fill: "#e0a458", "font-family": "'IBM Plex Mono',monospace", "font-size": 6, "text-anchor": "end" });
    path(svg, data.map((p, i) => `${i === 0 ? "M" : "L"}${xs(p[0])},${ys(p[1])}`).join(" "), { fill: "none", stroke: "#5fd4e8", "stroke-width": 1.5, "stroke-linejoin": "round" });
    // Peak marker.
    const peak = data.reduce((a, b) => (a[1] > b[1] ? a : b));
    svg.appendChild(el("circle", { cx: xs(peak[0]), cy: ys(peak[1]), r: 2.6, fill: "#c8f36b" }));
    txt(svg, xs(peak[0]) + 4, ys(peak[1]) - 4, "peak 1,568 N", { fill: "#c8f36b", "font-family": "'IBM Plex Mono',monospace", "font-size": 6.2 });
    txt(svg, margin.l, height - 5, "time (s)", { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 6.2 });
    txt(svg, 9, margin.t + plotH / 2, "force (N)", { fill: "#566873", "font-family": "'IBM Plex Mono',monospace", "font-size": 6.2, "text-anchor": "middle", transform: `rotate(-90 9 ${margin.t + plotH / 2})` });
    container.replaceChildren(svg);
  }

  function observe(container, render) {
    if (!container) return;
    let raf = null;
    const run = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(render); };
    if (window.ResizeObserver) new ResizeObserver(run).observe(container); else window.addEventListener("resize", run);
    if (document.fonts?.ready) document.fonts.ready.then(run);
    render();
  }

  observe(document.getElementById("load-chart"), () => renderLoad(document.getElementById("load-chart")));
  observe(document.getElementById("force-chart"), () => renderForce(document.getElementById("force-chart")));
})();
