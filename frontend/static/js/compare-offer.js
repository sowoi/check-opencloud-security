/*
 * "You scanned this instance earlier in this tab - see what changed."
 *
 * Scan, fix, scan again: the comparison is the question at the end of that,
 * and until now it needed the first uuid pasted by hand, which nobody had
 * kept. This file keeps it for them, in the one place that is already theirs.
 *
 * sessionStorage, not localStorage. The history is every finished scan of a
 * target this tab has shown, and each uuid in it is the credential for a
 * report (ADR 0007) - so it lives exactly as long as the tab, is never sent
 * to the server, and is pruned of anything whose result has expired, because
 * a link to a 404 is not an offer. Nothing is stored unless the page is a
 * finished scan, and nothing is offered unless a scan of the same target was
 * seen before this one.
 *
 * The order is the order the tab first saw each scan, not the order of
 * visits. Reloading the new report, or going back to the old one, therefore
 * keeps offering the scan that really came before it.
 *
 * Every sentence it writes was rendered by the server into a data attribute,
 * in the language the page is in. This file carries no English of its own.
 */
(function () {
    "use strict";

    var offer = document.querySelector("[data-compare-offer]");
    var uuid = document.body.getAttribute("data-scan-uuid");
    var expiresIn = parseInt(document.body.getAttribute("data-expires-in"), 10);
    if (!offer || !uuid) {
        return;
    }

    var STORAGE_KEY = "cos-scan-history";
    var PER_TARGET = 5;
    var TARGETS = 10;
    var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

    var target = offer.getAttribute("data-compare-target") || "";
    var sentence = offer.querySelector("[data-compare-offer-sentence]");
    var link = offer.querySelector("[data-compare-offer-link]");
    if (!target || !sentence || !link || !UUID.test(uuid)) {
        return;
    }

    function load() {
        try {
            var parsed = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || "{}");
            return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
        } catch (_error) {
            return {};
        }
    }

    function save(history) {
        try {
            window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
        } catch (_error) {
            // Storage refused (a private window, a full quota): the page is
            // exactly what it was without this script.
        }
    }

    // Anything malformed, expired or not a uuid is dropped on the way in, so
    // a value somebody edited by hand can only ever cost them the offer.
    function live(entries, now) {
        if (!Array.isArray(entries)) {
            return [];
        }
        return entries.filter(function (entry) {
            return entry && typeof entry.uuid === "string" && UUID.test(entry.uuid) &&
                typeof entry.seen === "number" && typeof entry.expires === "number" &&
                entry.expires > now;
        });
    }

    var now = Date.now();
    var history = load();
    Object.keys(history).forEach(function (key) {
        history[key] = live(history[key], now);
        if (!history[key].length) {
            delete history[key];
        }
    });

    var entries = history[target] || [];
    var position = -1;
    entries.forEach(function (entry, index) {
        if (entry.uuid === uuid) {
            position = index;
        }
    });
    var expires = now + (expiresIn > 0 ? expiresIn : 0) * 1000;
    if (position === -1) {
        entries.push({ uuid: uuid, seen: now, expires: expires });
        entries = entries.slice(-PER_TARGET);
        position = entries.length - 1;
    } else {
        entries[position].expires = expires;
    }
    // The target just shown moves to the end, so the ones pruned first are
    // the targets this tab has looked at least recently.
    delete history[target];
    history[target] = entries;
    var targets = Object.keys(history);
    targets.slice(0, Math.max(0, targets.length - TARGETS)).forEach(function (key) {
        delete history[key];
    });
    save(history);

    var earlier = position > 0 ? entries[position - 1] : null;
    if (!earlier) {
        return;
    }

    var time = "";
    try {
        time = new Date(earlier.seen).toLocaleTimeString(
            document.documentElement.lang || undefined,
            { hour: "2-digit", minute: "2-digit" }
        );
    } catch (_error) {
        time = new Date(earlier.seen).toLocaleTimeString();
    }

    sentence.textContent = (offer.getAttribute("data-compare-offer-text") || "")
        .replace("{time}", time);
    link.setAttribute(
        "href",
        "/compare?baseline=" + encodeURIComponent(earlier.uuid) +
            "&current=" + encodeURIComponent(uuid)
    );
    offer.hidden = false;
}());
