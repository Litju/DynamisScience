(function () {
  const toast = document.getElementById("toast");
  let timer;
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(timer);
    timer = setTimeout(() => toast.classList.remove("show"), 3200);
  }
  document.querySelectorAll("[data-toast]").forEach((el) => {
    el.addEventListener("click", (event) => {
      if (el.tagName === "A") event.preventDefault();
      showToast(el.dataset.toast);
    });
  });
  document.querySelectorAll(".tray-tabs button").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tray-tabs button").forEach((other) => other.setAttribute("aria-selected", String(other === tab)));
    });
  });
  document.querySelectorAll(".nav-tabs button").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".nav-tabs button").forEach((other) => other.setAttribute("aria-selected", String(other === tab)));
    });
  });

  const chart = document.getElementById("workspace-trajectory");
  if (chart) {
    RES588Charts.observeResize(chart, () => {
      RES588Charts.trajectory(chart, { theme: "workspace", annotationBackground: "rgba(12,16,21,.9)" });
    });
  }
  const forest = document.getElementById("workspace-forest");
  if (forest) {
    RES588Charts.observeResize(forest, () => {
      RES588Charts.forest(forest, { theme: "workspace", width: forest.clientWidth || 230, height: 76, pointStroke: "#111820" });
    });
  }
  const monitoring = document.getElementById("monitor-timeline");
  if (monitoring) {
    RES588Charts.observeResize(monitoring, () => {
      RES588Charts.monitoring(monitoring, { theme: "workspace", width: monitoring.clientWidth || 640, height: 290 });
    });
  }
})();
