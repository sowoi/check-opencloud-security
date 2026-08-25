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

    // Show how many checks are being waived without opening the panel. Both
    // wordings are rendered into the markup by the server, in the language
    // the page is in; this file only picks one and fills in the number.
    var details = form.querySelector("details.waivers");
    var summary = details && details.querySelector("summary");
    var idle = summary && (summary.getAttribute("data-waiver-label") || summary.textContent);
    var counted = summary && summary.getAttribute("data-waiver-label-selected");

    function countWaivers() {
        if (!summary) {
            return;
        }
        var checked = form.querySelectorAll('input[name="ignore_hardenings"]:checked').length;
        if (checked === 0 || !counted) {
            summary.textContent = idle;
            return;
        }
        summary.textContent = counted.replace("{count}", String(checked));
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
            button.textContent = button.getAttribute("data-busy-label") || button.textContent;
        }
    });

    countWaivers();
}());
