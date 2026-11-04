// M7b (T179): the quick-demo dashboard follows the plan live. Every 3 s it asks
// /plan/<uid>/log/?format=json for a stamp; when the stamp changes (the demo friend answered,
// proposed a time, or the plan is final) it fetches /d/ again and swaps the #dash-live block,
// so the agent log and the match card update without a page reload.
// M11c (T225), F4a (T253): the invite card has two buttons. Copy copies the link ('Link copied' for 2 s).
// Share opens the phone share sheet; it stays hidden when the browser has no navigator.share.

// F5a (T254): the tabs Upcoming / Past meetups / Activity. The hash picks the tab, with no reload;
// a hash that points inside a panel (#ask-12, #outing-7) opens that panel. Default: Upcoming.
// At 960 px and up CSS keeps Activity open in the right column, so the left shows Upcoming or Past.
var applyTab = (function () {
  var nav = document.querySelector(".tabs");
  if (!nav) return function () {};
  var NAMES = ["upcoming", "past", "activity"];
  var wide = window.matchMedia("(min-width: 960px)");
  function current() {
    var h = decodeURIComponent(window.location.hash.slice(1));
    if (NAMES.indexOf(h) >= 0) return h;
    var el = h && document.getElementById(h), panel = el && el.closest(".tab-panel");
    return panel ? panel.dataset.panel : "upcoming";
  }
  function apply() {
    var name = current();
    if (name === "activity" && wide.matches) name = "upcoming"; // Activity is the right column there
    document.querySelectorAll(".tab-panel").forEach(function (p) { p.hidden = p.dataset.panel !== name; });
    nav.querySelectorAll(".tab").forEach(function (t) {
      t.setAttribute("aria-selected", t.dataset.tab === name ? "true" : "false");
    });
  }
  nav.addEventListener("click", function (e) {
    var t = e.target.closest(".tab");
    if (!t) return;
    e.preventDefault();
    history.replaceState(null, "", "#" + t.dataset.tab);
    apply();
  });
  window.addEventListener("hashchange", apply);
  if (wide.addEventListener) wide.addEventListener("change", apply);
  apply();
  return apply;
})();

(function () {
  var share = document.getElementById("invite-share");
  if (share && navigator.share) share.hidden = false;
})();
document.addEventListener("click", function (e) {
  var btn = e.target.closest("#invite-copy, #invite-share");
  if (!btn) return;
  var url = btn.dataset.invite, copyBtn = document.getElementById("invite-copy");
  function done() {
    if (!copyBtn) return;
    copyBtn.textContent = "Link copied";
    setTimeout(function () { copyBtn.textContent = "Copy"; }, 2000);
  }
  function copy() {
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(url).then(done); return; }
    var t = document.createElement("textarea");
    t.value = url; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    try { document.execCommand("copy"); done(); } finally { t.remove(); }
  }
  if (btn.id === "invite-share" && navigator.share) {
    navigator.share({title: btn.dataset.title, url: url}).catch(function (err) {
      if (err && err.name !== "AbortError") copy();
    });
    return;
  }
  copy();
});

(function () {
  // G3 (T229): the group hint under the demo box puts its line into the box.
  var hint = document.getElementById("sandbox-group"), box = document.getElementById("sandbox-text");
  if (hint && box) hint.addEventListener("click", function () { box.value = hint.dataset.text; box.focus(); });
})();

(function () {
  var live = document.getElementById("dash-live");
  if (!live || !live.dataset.poll) return;
  var url = live.dataset.poll, stamp = null, timer = null, started = Date.now();
  var LIMIT = 15 * 60 * 1000; // stop after 15 minutes; a reload starts it again

  function swap() {
    return fetch(window.location.pathname, {credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        var next = new DOMParser().parseFromString(html, "text/html").getElementById("dash-live");
        if (next) { live.innerHTML = next.innerHTML; applyTab(); }
      });
  }

  function poll() {
    fetch(url, {credentials: "same-origin", headers: {Accept: "application/json"}})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return stop();
        var moved = stamp !== null && d.stamp !== stamp;
        stamp = d.stamp;
        var done = d.status !== "open" && d.status !== "asking" && d.status !== "confirmed";
        if (moved || done) swap();
        if (done || Date.now() - started > LIMIT) stop();
      })
      .catch(function () { /* a network blip: try again at the next beat */ });
  }

  function stop() { if (timer) clearInterval(timer); timer = null; }

  poll();
  timer = setInterval(poll, 3000);
})();

// F5b (T257): the 'Set up a meetup' modal. A <dialog> with showModal; Esc closes it (native), and
// so do the x button and a click on the backdrop. The date grid shows one month at a time; the
// picked day shows as 'Tue Nov 3' next to 'Day'. A post that missed a fact reloads the page with
// data-reopen, and the modal opens again at once with the text kept.
(function () {
  var dlg = document.getElementById("meet-dialog"), openBtn = document.getElementById("meet-open");
  if (!dlg || !openBtn || typeof dlg.showModal !== "function") return;
  var months = dlg.querySelectorAll(".cal-month"), picked = document.getElementById("meet-picked");
  function show(i) {
    months.forEach(function (m, k) { m.hidden = k !== i; });
  }
  function open() {
    var on = dlg.querySelector('input[name="date"]:checked'), m = on && on.closest(".cal-month");
    show(m ? Number(m.dataset.month) : 0);
    dlg.showModal();
    var box = document.getElementById("free-text");
    if (box && dlg.dataset.reopen) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
  }
  openBtn.addEventListener("click", open);
  document.getElementById("meet-close").addEventListener("click", function () { dlg.close(); });
  dlg.addEventListener("click", function (e) {
    if (e.target !== dlg) return;  // a click on the dialog box itself, not on the form, is the backdrop
    var r = dlg.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dlg.close();
  });
  dlg.addEventListener("click", function (e) {
    var b = e.target.closest(".cal-prev, .cal-next");
    if (!b || b.disabled) return;
    var i = Number(b.closest(".cal-month").dataset.month) + (b.classList.contains("cal-next") ? 1 : -1);
    show(Math.max(0, Math.min(months.length - 1, i)));
  });
  dlg.addEventListener("change", function (e) {
    if (e.target.name !== "date" || !picked) return;
    picked.textContent = e.target.dataset.label;
    var hint = document.getElementById("meet-hint");
    if (hint) hint.remove();
  });
  if (dlg.dataset.reopen) open();
})();

// F3a (T259): copy the person's @handle from the header.
document.addEventListener("click", function (e) {
  var btn = e.target.closest("#handle-copy");
  if (!btn) return;
  var text = btn.dataset.handle;
  function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 2000); }
  if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done); return; }
  var t = document.createElement("textarea");
  t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.select();
  try { document.execCommand("copy"); done(); } finally { t.remove(); }
});
