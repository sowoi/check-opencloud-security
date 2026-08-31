/*
 * The wait before this instance can be scanned again.
 *
 * The server rendered the remaining seconds into the card; everything after
 * that happens here, with no further request. Reading the limit costs nothing
 * on the server, but asking every second would turn a countdown into traffic,
 * and the answer is arithmetic the browser can do.
 *
 * The deadline is computed once, as a wall-clock instant, and every tick is
 * measured against it rather than counted down. A laptop that sleeps for ten
 * minutes wakes up with the right answer instead of ten minutes of missed
 * ticks; an interval that drifts corrects itself on the next one.
 *
 * The button starts enabled in the markup and is disabled from here. A reader
 * without scripting therefore always has a working button - they may meet the
 * rate limit's own friendly page, which is a better outcome than a control
 * this file was never loaded to release.
 *
 * The wait is not a promise. It is the longer of two limits as they stood
 * when the page was rendered, and somebody else may claim the instance's slot
 * in between. Reaching zero re-enables the button; it does not guarantee the
 * next submission is accepted, and the 429 explains itself if it is not.
 *
 * Every sentence it writes was rendered by the server into a data attribute,
 * in the language the page is in. This file carries no English of its own.
 */
(function () {
    "use strict";

    var card = document.querySelector("[data-rescan-after]");
    if (!card) {
        return;
    }

    var button = card.querySelector("[data-rescan-button]");
    var note = document.getElementById("rescan-note");
    var seconds = parseInt(card.getAttribute("data-rescan-after"), 10);
    if (!button || !note || !(seconds > 0)) {
        return;
    }

    var deadline = Date.now() + seconds * 1000;
    var timer = null;

    function phrase(name) {
        var value = card.getAttribute("data-" + name);
        return value === null ? "" : value;
    }

    function clock(remaining) {
        var minutes = Math.floor(remaining / 60);
        var rest = remaining % 60;
        return minutes + ":" + (rest < 10 ? "0" + rest : String(rest));
    }

    function ready() {
        window.clearInterval(timer);
        button.disabled = false;
        button.removeAttribute("data-waiting");
        note.textContent = phrase("rescan-ready");
    }

    function tick() {
        // Ceil, so that the last second is shown as 0:01 rather than 0:00 for
        // a second during which the button is still disabled.
        var remaining = Math.ceil((deadline - Date.now()) / 1000);
        if (remaining <= 0) {
            ready();
            return;
        }
        note.textContent = phrase("rescan-wait").replace("{countdown}", clock(remaining));
    }

    button.disabled = true;
    button.setAttribute("data-waiting", "true");
    tick();
    timer = window.setInterval(tick, 1000);
}());
