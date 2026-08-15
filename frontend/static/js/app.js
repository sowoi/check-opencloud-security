/*
 * Landing page niceties. Nothing here is required for the form to work: it is
 * a plain POST, and it submits fine with this file blocked.
 */
(function () {
    "use strict";

    var form = document.querySelector(".scan-form");
    if (!form) {
        return;
    }

    // Show how many checks are being waived without opening the panel.
    var details = form.querySelector("details.waivers");
    var summary = details && details.querySelector("summary");
    var label = summary && summary.textContent;

    function countWaivers() {
        if (!summary) {
            return;
        }
        var checked = form.querySelectorAll('input[name="ignore_hardenings"]:checked').length;
        summary.textContent = checked === 0
            ? label
            : label.replace("(optional)", "(" + checked + " selected)");
    }

    form.addEventListener("change", function (event) {
        if (event.target && event.target.name === "ignore_hardenings") {
            countWaivers();
        }
    });

    // A scan takes a few seconds; a button that stays clickable invites a
    // second submission, which the target rate limit would then refuse.
    form.addEventListener("submit", function () {
        var button = form.querySelector('button[type="submit"]');
        if (button) {
            button.disabled = true;
            button.textContent = "Starting audit...";
        }
    });

    countWaivers();
}());
