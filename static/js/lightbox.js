/**
 * Gallery lightbox — click-to-expand for media_grid.html photos.
 *
 * The one job of this script is to point the shared <dialog> (templates/
 * partials/lightbox.html) at whichever photo was clicked and call the
 * native `.showModal()` / `.close()` on it. Esc-to-close, focus trapping,
 * and the backdrop are all native <dialog> behaviour — nothing here
 * reimplements them, matching the minimal-JS bias theme-toggle.js sets out
 * (see .claude/plans/03-design-system.md).
 *
 * Delegated to `document` rather than binding a listener per trigger: the
 * grid can render any number of photos across any number of media_grid.html
 * instances on a page, and this way none of them need per-element JS.
 */
(function () {
  "use strict";

  function init() {
    var dialog = document.getElementById("lightbox");
    if (!dialog) {
      return;
    }
    var image = dialog.querySelector("[data-lightbox-image]");
    var closeButton = dialog.querySelector("[data-lightbox-close]");

    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-lightbox-trigger]");
      if (!trigger) {
        return;
      }
      image.src = trigger.getAttribute("data-lightbox-src") || "";
      image.alt = trigger.getAttribute("data-lightbox-alt") || "";
      dialog.showModal();
    });

    if (closeButton) {
      closeButton.addEventListener("click", function () {
        dialog.close();
      });
    }

    // Click on the backdrop (the <dialog> element itself, outside its
    // content box) closes it — `showModal()` doesn't do this on its own.
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        dialog.close();
      }
    });

    // Drop the image src on close so a closed-but-still-loading photo
    // doesn't keep downloading, and the dialog doesn't briefly flash the
    // previous photo the next time it opens.
    dialog.addEventListener("close", function () {
      image.src = "";
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
