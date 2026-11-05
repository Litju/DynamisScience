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

  const labToggle = document.getElementById("lab-toggle");
  if (labToggle) {
    labToggle.addEventListener("click", () => {
      const open = document.body.classList.toggle("lab-open");
      labToggle.setAttribute("aria-expanded", String(open));
      labToggle.textContent = open ? "Close lab" : "Model lab";
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("lab-open")) {
        document.body.classList.remove("lab-open");
        labToggle.setAttribute("aria-expanded", "false");
        labToggle.textContent = "Model lab";
      }
    });
  }

  document.querySelectorAll(".lab-tabs button").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".lab-tabs button").forEach((other) => other.setAttribute("aria-selected", String(other === tab)));
      document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== tab.dataset.pane;
      });
    });
  });

  const chart = document.getElementById("fieldlab-trajectory");
  if (chart) {
    RES588Charts.observeResize(chart, () => {
      RES588Charts.trajectory(chart, { theme: "fieldlab", annotationBackground: "rgba(247,241,227,.94)" });
    });
  }
})();
