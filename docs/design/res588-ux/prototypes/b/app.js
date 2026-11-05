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
  document.querySelectorAll(".toc a").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".toc a").forEach((other) => other.classList.toggle("active", other === link));
      const href = link.getAttribute("href");
      if (href && href.startsWith("#")) {
        const target = document.querySelector(href);
        const details = target && target.closest("details");
        if (details) details.open = true;
      }
    });
  });

  const chart = document.getElementById("notebook-trajectory");
  if (chart) {
    RES588Charts.observeResize(chart, () => {
      RES588Charts.trajectory(chart, { theme: "notebook", annotationBackground: "rgba(251,248,238,.92)" });
    });
  }
})();
