/*
 * The scheme a visitor chose, applied before the page is drawn.
 *
 * The default is, and stays, the operating system's: with nothing stored
 * this file writes no scheme at all and the `prefers-color-scheme` blocks in
 * app.css are the only thing that decides, exactly as they did before there
 * was a switch. An override is a deliberate act, it lives only in this
 * browser, and it is the one thing this file reads.
 *
 * It is loaded without `defer` - the only script on the site that is - because
 * it has to win the race against the first paint. A deferred one would run
 * after the page had already been painted in the system's scheme, and a
 * visitor who chose the other one would meet a flash of the wrong page on
 * every single navigation.
 *
 * It also marks the document, which is what reveals the switch itself: a
 * button that only works with scripting should only appear with scripting.
 * The mark is set whether or not an override exists, because the button works
 * either way - the reading of storage is what may fail, not the switching.
 */
(function () {
    "use strict";

    var root = document.documentElement;

    try {
        var stored = window.localStorage.getItem("theme");
        if (stored === "light" || stored === "dark") {
            root.setAttribute("data-theme", stored);
        }
    } catch (error) {
        // Storage can be unavailable outright - private windows, storage
        // turned off, a browser that throws rather than returns null. The
        // system preference still applies, so there is nothing to recover
        // from and nothing to tell anybody.
    }

    root.setAttribute("data-theme-ready", "true");
}());
