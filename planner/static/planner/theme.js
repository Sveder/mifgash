/* Theme: system by default; the toggle saves "light" or "dark" in localStorage "mif-theme".
   Load in <head> without defer so the page never flashes the wrong theme. */
(function () {
  var KEY = "mif-theme", root = document.documentElement;
  try { var saved = localStorage.getItem(KEY); if (saved) root.dataset.theme = saved; } catch (e) {}
  function current() {
    return root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function label(btn) {
    var next = current() === "dark" ? "light" : "dark";
    btn.setAttribute("aria-label", "Switch to " + next + " mode");
    btn.innerHTML = current() === "dark"
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      label(btn);
      btn.addEventListener("click", function () {
        root.dataset.theme = current() === "dark" ? "light" : "dark";
        try { localStorage.setItem(KEY, root.dataset.theme); } catch (e) {}
        document.querySelectorAll("[data-theme-toggle]").forEach(label);
      });
    });
  });
})();
