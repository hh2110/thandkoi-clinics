/*
 * Circle of Care — reveal a stage's detail in the hub on hover / focus / tap.
 *
 * Progressive enhancement: the section renders fully without this script
 * (wheel, on-ring names, and the default hub). This only adds the reveal.
 * Idempotent and HTMX-friendly — safe to call again after swaps.
 */
(function () {
  "use strict";

  function initCircle(root) {
    if (root.dataset.cocReady) return;
    root.dataset.cocReady = "1";

    var labels = Array.prototype.slice.call(root.querySelectorAll("[data-coc-stage]"));
    var segs = Array.prototype.slice.call(root.querySelectorAll("[data-coc-seg]"));
    var defaultEl = root.querySelector("[data-coc-default]");
    var detailEl = root.querySelector("[data-coc-detail]");
    var nameEl = root.querySelector("[data-coc-detail-name]");
    var descEl = root.querySelector("[data-coc-detail-desc]");
    if (!labels.length || !detailEl) return;

    var pinned = null; // index kept after a click/tap (for touch)

    function show(index) {
      var label = labels[index];
      if (!label) return;
      nameEl.textContent = label.getAttribute("data-coc-name");
      descEl.textContent = label.getAttribute("data-coc-desc");
      defaultEl.hidden = true;
      detailEl.hidden = false;
      root.classList.add("is-selecting");
      labels.forEach(function (l, i) { l.classList.toggle("is-active", i === index); });
      segs.forEach(function (s, i) { s.classList.toggle("is-active", i === index); });
    }

    function reset() {
      if (pinned !== null) { show(pinned); return; }
      defaultEl.hidden = false;
      detailEl.hidden = true;
      root.classList.remove("is-selecting");
      labels.forEach(function (l) { l.classList.remove("is-active"); });
      segs.forEach(function (s) { s.classList.remove("is-active"); });
    }

    function wire(el, index) {
      el.addEventListener("mouseenter", function () { show(index); });
      el.addEventListener("focus", function () { show(index); });
      el.addEventListener("mouseleave", reset);
      el.addEventListener("blur", reset);
      el.addEventListener("click", function () {
        pinned = pinned === index ? null : index;
        pinned === null ? reset() : show(index);
      });
    }

    labels.forEach(function (label, i) {
      wire(label, i);
      var seg = segs[i];
      if (seg) {
        seg.style.cursor = "pointer";
        wire(seg, i); // focus/blur are no-ops here — an SVG <path> isn't focusable.
      }
    });
  }

  function initAll(scope) {
    (scope || document).querySelectorAll("[data-coc]").forEach(initCircle);
  }

  if (document.readyState !== "loading") initAll();
  else document.addEventListener("DOMContentLoaded", function () { initAll(); });

  // Re-init after HTMX swaps.
  document.body && document.body.addEventListener("htmx:afterSwap", function (e) {
    initAll(e.target);
  });
})();
