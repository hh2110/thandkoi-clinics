/*
 * Funding-mix chart (Plan 13) — hover tooltip for the reports-index chart.
 *
 * Progressive enhancement: the chart, its bars, axis labels, and the
 * "view as table" fallback all render fully without this script. This only
 * adds the hover tooltip on top. Idempotent and HTMX-friendly — safe to
 * call again after swaps (mirrors circle-of-care.js).
 */
(function () {
  "use strict";

  var tooltip = null;

  function getTooltip() {
    if (tooltip) return tooltip;
    tooltip = document.createElement("div");
    tooltip.className = "ri-funding-mix__tooltip";
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function showTip(evt, hit, labels) {
    var tip = getTooltip();
    var date = hit.getAttribute("data-date");
    var zakat = hit.getAttribute("data-zakat");
    var regular = hit.getAttribute("data-regular");
    var total = hit.getAttribute("data-total");
    tip.textContent = date + ": " + labels.zakat + " " + zakat +
      " · " + labels.regular + " " + regular +
      " · " + labels.total + " " + total;
    tip.style.left = evt.clientX + "px";
    tip.style.top = evt.clientY + "px";
    tip.classList.add("is-visible");
  }

  function hideTip() {
    if (tooltip) tooltip.classList.remove("is-visible");
  }

  function initChart(svg) {
    if (svg.dataset.fmReady) return;
    svg.dataset.fmReady = "1";

    var labels = {
      zakat: svg.getAttribute("data-label-zakat"),
      regular: svg.getAttribute("data-label-regular"),
      total: svg.getAttribute("data-label-total"),
    };
    var hits = Array.prototype.slice.call(svg.querySelectorAll("[data-funding-mix-hit]"));
    hits.forEach(function (hit) {
      hit.addEventListener("mousemove", function (e) { showTip(e, hit, labels); });
      hit.addEventListener("mouseleave", hideTip);
    });
  }

  function initAll(scope) {
    (scope || document).querySelectorAll("[data-funding-mix]").forEach(initChart);
  }

  if (document.readyState !== "loading") initAll();
  else document.addEventListener("DOMContentLoaded", function () { initAll(); });

  // Re-init after HTMX swaps.
  document.body && document.body.addEventListener("htmx:afterSwap", function (e) {
    initAll(e.target);
  });
})();
