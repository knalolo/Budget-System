/**
 * Application-level JavaScript utilities.
 *
 * HTMX and Alpine.js are loaded via CDN; this file provides lightweight
 * helpers and HTMX event hooks.
 */

/* -----------------------------------------------------------------------
 * HTMX: preserve scroll position on partial page swaps
 * ----------------------------------------------------------------------- */

document.addEventListener("htmx:beforeSwap", function (evt) {
    // Store scroll position before swap
    evt.detail._scrollY = window.scrollY;
});

document.addEventListener("htmx:afterSwap", function (evt) {
    // Restore scroll position when desired
    if (evt.detail._scrollY !== undefined && evt.target.dataset.preserveScroll) {
        window.scrollTo(0, evt.detail._scrollY);
    }
});

/* -----------------------------------------------------------------------
 * HTMX: auto-dismiss flash messages after 5 seconds
 * ----------------------------------------------------------------------- */

document.addEventListener("htmx:afterSettle", dismissMessages);
document.addEventListener("DOMContentLoaded", dismissMessages);

function dismissMessages() {
    const container = document.getElementById("messages");
    if (!container) return;

    setTimeout(function () {
        const messages = container.querySelectorAll("[x-data]");
        messages.forEach(function (el) {
            // Trigger Alpine's show=false via a synthetic click on the close button
            const closeBtn = el.querySelector("button");
            if (closeBtn) closeBtn.click();
        });
    }, 5000);
}

/* -----------------------------------------------------------------------
 * CSRF token helper for fetch() calls
 * ----------------------------------------------------------------------- */

function getCsrfToken() {
    const cookie = document.cookie.split(";").find((c) => c.trim().startsWith("csrftoken="));
    return cookie ? cookie.split("=")[1] : "";
}

/* -----------------------------------------------------------------------
 * Confirmation dialog utility (used by delete buttons)
 * ----------------------------------------------------------------------- */

function confirmAction(message) {
    return window.confirm(message || "Are you sure?");
}
