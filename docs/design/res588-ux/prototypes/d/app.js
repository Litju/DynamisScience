(function () {
  const toast = document.getElementById("toast");
  let timer;
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(timer);
    timer = setTimeout(() => toast.classList.remove("show"), 3400);
  }
  document.querySelectorAll("[data-toast]").forEach((el) => {
    el.addEventListener("click", (event) => {
      if (el.tagName === "A") event.preventDefault();
      showToast(el.dataset.toast);
    });
  });

  const toggle = document.getElementById("outline-toggle");
  const panel = document.getElementById("outline-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      const open = panel.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("mousedown", (event) => {
      if (!panel.classList.contains("open")) return;
      if (panel.contains(event.target) || toggle.contains(event.target)) return;
      panel.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        panel.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  const notesToggle = document.getElementById("notes-toggle");
  if (notesToggle) {
    notesToggle.addEventListener("click", () => {
      const open = document.body.classList.toggle("notes-open");
      notesToggle.setAttribute("aria-expanded", String(open));
      notesToggle.textContent = open ? "Close notes" : "Notes · 4";
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("notes-open")) {
        document.body.classList.remove("notes-open");
        notesToggle.setAttribute("aria-expanded", "false");
        notesToggle.textContent = "Notes · 4";
      }
    });
  }

  const chart = document.getElementById("atelier-trajectory");
  if (chart) {
    RES588Charts.observeResize(chart, () => {
      RES588Charts.trajectory(chart, { theme: "atelier", annotationBackground: "rgba(251,248,239,.94)" });
    });
  }
  const monitor = document.getElementById("atelier-monitor");
  if (monitor) {
    RES588Charts.observeResize(monitor, () => {
      RES588Charts.monitoring(monitor, { theme: "atelier", width: monitor.clientWidth || 900, height: 275 });
    });
  }
  const reportChart = document.getElementById("atelier-report-chart");
  if (reportChart) {
    RES588Charts.observeResize(reportChart, () => {
      RES588Charts.trajectory(reportChart, { theme: "atelier", annotationBackground: "rgba(251,248,239,.94)" });
    });
  }
})();
