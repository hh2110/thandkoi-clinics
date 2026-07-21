/*
 * Primary-nav disclosure fallback.
 *
 * The nav is a <details>/<summary> disclosure: a "Menu" hamburger on small
 * screens that lays out inline on desktop (the <summary> is hidden by CSS).
 * The CSS keeps a *closed* <details> laid out on desktop via ::details-content,
 * but older browsers don't support that pseudo-element and would collapse the
 * inline menu to nothing. This opens the disclosure on desktop and collapses it
 * back to the hamburger on small screens, so the menu works everywhere —
 * progressive enhancement layered on top of the CSS.
 */
(function () {
  "use strict";
  var nav = document.querySelector(".primary-nav");
  if (!nav) {
    return;
  }
  var desktop = window.matchMedia("(min-width: 56rem)");
  function sync() {
    nav.open = desktop.matches;
  }
  sync();
  if (typeof desktop.addEventListener === "function") {
    desktop.addEventListener("change", sync);
  } else if (typeof desktop.addListener === "function") {
    // Safari < 14 and other older engines.
    desktop.addListener(sync);
  }
})();
