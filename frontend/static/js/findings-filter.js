/*
 * The severity counters, used as a filter over the findings.
 *
 * A long report is read by looking for one thing at a time - the critical
 * entries first, the informational ones last or never - and the counters at
 * the top of the verdict already say how many of each there are. Pressing one
 * hides the rest of the list rather than sending the reader hunting through
 * it, and pressing it again gives the list back.
 *
 * Nothing is fetched and nothing is recalculated: every entry is already on
 * the page, tagged with the severity the server gave it, so this only ever
 * sets `hidden`. The counts themselves are the server's and are never
 * rewritten here - a filter that edited the numbers it filters by would be
 * the one thing on this page that could disagree with the scan.
 *
 * Every sentence it writes was rendered by the server, in the language the
 * page is in: the template around the severity, and the severity itself from
 * the pressed counter's own label. This file carries no English of its own.
 */
(function () {
    "use strict";

    var buttons = document.querySelectorAll(".counter[data-filter]");
    var list = document.querySelector("[data-findings-list]");
    if (!buttons.length || !list) {
        return;
    }

    var items = list.querySelectorAll(".finding[data-tag]");
    var status = document.getElementById("findings-filter-status");
    var statusText = document.getElementById("findings-filter-text");
    var clear = status ? status.querySelector("[data-filter-clear]") : null;
    var active = null;

    function each(nodes, visit) {
        Array.prototype.forEach.call(nodes, visit);
    }

    // The severity as this page spells it, taken from the counter that names
    // it rather than from the tag underneath, which is an identifier.
    function label(value) {
        var found = "";
        each(buttons, function (button) {
            if (button.getAttribute("data-filter") === value) {
                var name = button.querySelector("span");
                found = name ? name.textContent : value;
            }
        });
        return found;
    }

    function describe() {
        if (!status || !statusText) {
            return;
        }
        if (!active) {
            status.hidden = true;
            statusText.textContent = "";
            return;
        }
        var template = status.getAttribute("data-filter-active") || "";
        statusText.textContent = template.replace("{severity}", label(active));
        status.hidden = false;
    }

    function apply() {
        each(items, function (item) {
            item.hidden = active !== null && item.getAttribute("data-tag") !== active;
        });
        each(buttons, function (button) {
            button.setAttribute(
                "aria-pressed",
                button.getAttribute("data-filter") === active ? "true" : "false"
            );
        });
        describe();
    }

    each(buttons, function (button) {
        button.addEventListener("click", function () {
            var value = button.getAttribute("data-filter");
            // Pressing the counter that is already on is how the reader asks
            // for the whole list back, without having to find another control.
            active = active === value ? null : value;
            apply();
        });
    });

    if (clear) {
        clear.addEventListener("click", function () {
            active = null;
            apply();
        });
    }
}());
