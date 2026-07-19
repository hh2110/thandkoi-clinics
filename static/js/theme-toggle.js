/**
 * Theme toggle — the one deliberate JS dependency in Plan 03's otherwise
 * no-JS design system (see .claude/plans/03-design-system.md).
 *
 * Pairs with the inline anti-FOUC script in templates/base.html's <head>,
 * which sets `data-theme` on <html> synchronously before first paint by
 * reading the same localStorage key. This file only has to handle the click.
 *
 * Progressive enhancement: the button markup in
 * templates/partials/theme_toggle.html starts `hidden`. If this script never
 * runs (JS disabled/blocked), the button stays hidden and the site simply
 * follows the OS `prefers-color-scheme` via tokens.css's media query.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "thandkoi-theme";

  function getStoredTheme() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      return null;
    }
  }

  function setStoredTheme(theme) {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (err) {
      /* Storage unavailable (private mode, disabled cookies, etc.) — the
         toggle still works for the current page view, it just won't
         persist across reloads. */
    }
  }

  function currentTheme() {
    var stored = getStoredTheme();
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
  }

  function initToggle(button) {
    var label = button.querySelector("[data-theme-toggle-label]");

    function syncButton(theme) {
      var isDark = theme === "dark";
      button.setAttribute("aria-pressed", String(isDark));
      if (label) {
        label.textContent = isDark ? "Dark theme" : "Light theme";
      }
    }

    syncButton(currentTheme());
    button.hidden = false;

    button.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      applyTheme(next);
      setStoredTheme(next);
      syncButton(next);
    });
  }

  function init() {
    var button = document.querySelector("[data-theme-toggle]");
    if (button) {
      initToggle(button);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
