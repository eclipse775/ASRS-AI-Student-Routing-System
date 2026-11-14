/* Campus Route theme controller.
   Loaded synchronously in <head> (CSP allows only external scripts) so the
   correct theme is on <html> before the first paint: no white flash. */
(function () {
  "use strict";
  var KEY = "cr-theme";
  var root = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function stored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : "system";
    } catch (e) { return "system"; }
  }

  var pref = stored();

  function resolve(p) {
    return p === "system" ? (mq && mq.matches ? "dark" : "light") : p;
  }

  function apply() {
    var t = resolve(pref);
    root.setAttribute("data-theme", t);
    root.setAttribute("data-pref", pref);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "dark" ? "#0d1513" : "#f6f7f3");
  }

  /* Keeps every toggle / theme card in the DOM in sync with the current state. */
  function sync() {
    var dark = resolve(pref) === "dark";
    var label = dark ? "Switch to light theme" : "Switch to dark theme";
    document.querySelectorAll(".theme-toggle").forEach(function (el) {
      el.setAttribute("aria-checked", String(dark));
      el.setAttribute("aria-label", label);
      el.setAttribute("title", label);
    });
    document.querySelectorAll(".theme-card[data-pref]").forEach(function (el) {
      var on = el.getAttribute("data-pref") === pref;
      el.setAttribute("aria-checked", String(on));
      el.classList.toggle("on", on);
    });
  }

  apply();

  if (mq) {
    var onSystemChange = function () {
      if (pref === "system") { apply(); sync(); }
    };
    if (mq.addEventListener) mq.addEventListener("change", onSystemChange);
    else if (mq.addListener) mq.addListener(onSystemChange);
  }

  function set(next, origin) {
    var before = resolve(pref);
    pref = next;
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch (e) { /* private mode: the choice just won't persist */ }
    var after = resolve(pref);

    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (before === after || reduce) { apply(); sync(); return; }

    if (document.startViewTransition) {
      /* A circle grows from the button that was clicked and reveals the new theme. */
      var r = origin && origin.getBoundingClientRect ? origin.getBoundingClientRect() : null;
      var x = r ? r.left + r.width / 2 : window.innerWidth / 2;
      var y = r ? r.top + r.height / 2 : window.innerHeight / 2;
      var end = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
      root.classList.add("theme-vt");
      var vt = document.startViewTransition(function () { apply(); sync(); });
      vt.ready.then(function () {
        root.animate(
          { clipPath: ["circle(0px at " + x + "px " + y + "px)", "circle(" + end + "px at " + x + "px " + y + "px)"] },
          { duration: 700, easing: "cubic-bezier(.4,0,.2,1)", pseudoElement: "::view-transition-new(root)" }
        );
      }).catch(function () {});
      vt.finished.then(function () { root.classList.remove("theme-vt"); },
                       function () { root.classList.remove("theme-vt"); });
    } else {
      /* Fallback: smooth cross-fade of colors. */
      root.classList.add("theme-anim");
      apply(); sync();
      setTimeout(function () { root.classList.remove("theme-anim"); }, 500);
    }
  }

  window.CRTheme = {
    set: set,
    sync: sync,
    toggle: function (origin) { set(resolve(pref) === "dark" ? "light" : "dark", origin); },
    get pref() { return pref; },
    get resolved() { return resolve(pref); }
  };
})();
