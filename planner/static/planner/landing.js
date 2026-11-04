// T122: copy the agents.md link. The page shows the public host; the copy uses this page's origin.
document.addEventListener("click", function (e) {
  var btn = e.target.closest("[data-copy]");
  if (!btn) return;
  // F2a (T250): a button with data-copy-text copies that text (the /setup/ prompt); else the agents.md link.
  var url = btn.getAttribute("data-copy-text") || (location.origin + "/agents.md");
  function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1600); }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(done);
    return;
  }
  var t = document.createElement("textarea");
  t.value = url; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.select();
  try { document.execCommand("copy"); done(); } finally { t.remove(); }
});

// M8b (T182): the explainer runs on CSS alone. This only restarts the loop at frame 1 when the
// explainer first scrolls into view and when the tab is shown again, so a visitor sees it from the start.
(function () {
  var svg = document.querySelector("svg.xp");
  if (!svg) return;
  function restart() {
    svg.classList.remove("play");
    void svg.getBoundingClientRect();
    svg.classList.add("play");
  }
  if ("IntersectionObserver" in window) {
    var seen = false;
    new IntersectionObserver(function (es, obs) {
      if (es[0].isIntersecting && !seen) { seen = true; restart(); obs.disconnect(); }
    }, { threshold: 0.4 }).observe(svg);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) restart(); });
})();
