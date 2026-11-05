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
      if (el.tagName === "BUTTON" && !el.getAttribute("type")) event.preventDefault();
      showToast(el.dataset.toast);
    });
  });
  document.querySelectorAll(".insp-tabs button").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".insp-tabs button").forEach((other) => other.setAttribute("aria-selected", String(other === tab)));
    });
  });
  document.querySelectorAll(".activity button[data-toast]").forEach((button) => {
    button.addEventListener("click", () => button.classList.remove("active"));
  });

  const chart = document.getElementById("trajectory");
  if (chart) {
    RES588Charts.observeResize(chart, () => {
      RES588Charts.trajectory(chart, { theme: "studio", annotationBackground: "rgba(12,16,18,.88)" });
    });
  }
})();
