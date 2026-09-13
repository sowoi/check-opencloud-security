/*
 * The warning before a finished report disappears.
 *
 * A result lives for the operator's TTL and then the link is a 404 - which is
 * the privacy promise, and also a report somebody had open in a tab and meant
 * to download "later". This keeps the two readings of that deadline current
 * on a page that is no longer polling: the expiry line at the foot, and the
 * warning near the top that appears for the last few minutes with a way to
 * keep a copy.
 *
 * A scan still queued or running is left alone. scan.js already rewrites the
 * expiry line from the server's own figure on every poll, and the page
 * reloads the moment the scan settles, carrying a fresh deadline with it.
 *
 * The deadline is taken once, as a wall-clock instant, from the seconds the
 * server rendered. A laptop that sleeps through the end wakes to "gone"
 * rather than to a countdown that stopped where it was.
 *
 * Every sentence it writes was rendered by the server into a data attribute,
 * in the language the page is in. This file carries no English of its own.
 */
(function () {
    "use strict";

    var body = document.body;
    var state = body.getAttribute("data-scan-state");
    var seconds = parseInt(body.getAttribute("data-expires-in"), 10);
    if ((state !== "completed" && state !== "failed") || !(seconds > 0)) {
        return;
    }

    var warning = document.querySelector("[data-expiry-warning]");
    var warningText = warning ? warning.querySelector("[data-expiry-warning-text]") : null;
    var action = warning ? warning.querySelector("[data-expiry-warning-action]") : null;
    var line = document.getElementById("expiry-note");
    var lineBox = line ? line.parentNode : null;
    if (!warning && !line) {
        return;
    }

    var TICK_MS = 15000;
    var deadline = Date.now() + seconds * 1000;
    var warnAfter = warning ? parseInt(warning.getAttribute("data-expiry-warn-after"), 10) : 0;
    var timer = null;
    var shown = null;

    function phrase(element, name) {
        var value = element ? element.getAttribute("data-" + name) : null;
        return value === null ? "" : value;
    }

    function minutesPhrase(element, prefix, minutes) {
        return minutes === 1
            ? phrase(element, prefix + "-one")
            : phrase(element, prefix + "-many").replace("{minutes}", String(minutes));
    }

    // Written only when the words change, because both places are live
    // regions and a sentence rewritten to itself can be announced again.
    function write(element, text) {
        if (element && text && element.textContent !== text) {
            element.textContent = text;
        }
    }

    function tick() {
        var remaining = Math.ceil((deadline - Date.now()) / 1000);

        if (remaining <= 0) {
            window.clearInterval(timer);
            document.removeEventListener("visibilitychange", tick);
            if (warning) {
                write(warningText, phrase(warning, "expiry-gone"));
                if (action) {
                    // The downloads are gone with the result.
                    action.hidden = true;
                }
                warning.hidden = false;
            }
            write(line, phrase(warning, "expiry-gone"));
            return;
        }

        // The foot line counts in whole minutes the way the server rendered
        // it; the warning rounds up, so it never says "0 minutes".
        var floor = Math.max(1, Math.floor(remaining / 60));
        var ceil = Math.max(1, Math.ceil(remaining / 60));
        write(line, minutesPhrase(lineBox, "expiry", floor));

        if (warning && warnAfter > 0 && remaining <= warnAfter) {
            if (shown !== ceil) {
                write(warningText, minutesPhrase(warning, "expiry-warning", ceil));
                shown = ceil;
            }
            warning.hidden = false;
        }
    }

    tick();
    timer = window.setInterval(tick, TICK_MS);
    // A tab brought back to the front is answered at once, not at the next
    // tick, since that is the moment somebody reads it.
    document.addEventListener("visibilitychange", tick);
}());
