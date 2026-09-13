/*
 * The last settings, offered back.
 *
 * On submit, the release track, the output format and the waivers chosen are
 * written to this browser's localStorage. On the next visit, when what is
 * remembered differs from what the form shows, one line says what it was and
 * offers to apply it, or to forget it. Nothing is ever applied unasked: a
 * form that fills itself in is a form whose choices nobody made.
 *
 * Never the address. The instance a visitor scans is theirs to have the
 * browser remember, through its own autocomplete and its own "clear history";
 * a second copy kept here would outlive both. The settings stay in the
 * browser, are never sent anywhere but in the form the visitor submits, and
 * are read back defensively - a waiver the catalogue no longer lists, or a
 * track that is gone, is simply not applied.
 *
 * Every sentence it writes was rendered by the server into a data attribute,
 * in the language the page is in. This file carries no English of its own.
 */
(function () {
    "use strict";

    var form = document.querySelector(".scan-form");
    var offer = document.querySelector("[data-remember]");
    if (!form || !offer) {
        return;
    }

    var STORAGE_KEY = "cos-form-settings";
    var MAX_WAIVERS = 200;

    var track = form.querySelector('select[name="release_track"]');
    var format = form.querySelector('select[name="output_format"]');
    var text = offer.querySelector("[data-remember-text]");
    var apply = offer.querySelector("[data-remember-apply]");
    var forget = offer.querySelector("[data-remember-forget]");
    var details = form.querySelector("details.waivers");

    function boxes() {
        return Array.prototype.slice.call(
            form.querySelectorAll('input[type="checkbox"][name="ignore_hardenings"]')
        );
    }

    function hasOption(select, value) {
        return !!select && Array.prototype.some.call(select.options, function (option) {
            return option.value === value;
        });
    }

    function optionLabel(select, value) {
        var label = "";
        Array.prototype.forEach.call(select ? select.options : [], function (option) {
            if (option.value === value) {
                label = option.textContent.trim();
            }
        });
        return label;
    }

    function current() {
        return {
            track: track ? track.value : "",
            format: format ? format.value : "",
            waivers: boxes().filter(function (box) {
                return box.checked;
            }).map(function (box) {
                return box.value;
            }).sort()
        };
    }

    // Reduced to what this page can actually show, so a stale entry costs the
    // visitor that entry and nothing else.
    function load() {
        var raw;
        try {
            raw = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
        } catch (_error) {
            return null;
        }
        if (!raw || typeof raw !== "object") {
            return null;
        }
        var known = {};
        boxes().forEach(function (box) {
            known[box.value] = true;
        });
        var waivers = Array.isArray(raw.waivers) ? raw.waivers : [];
        return {
            track: typeof raw.track === "string" && hasOption(track, raw.track)
                ? raw.track : (track ? track.value : ""),
            format: typeof raw.format === "string" && hasOption(format, raw.format)
                ? raw.format : (format ? format.value : ""),
            waivers: waivers.slice(0, MAX_WAIVERS).filter(function (name, index) {
                return typeof name === "string" && known[name] === true &&
                    waivers.indexOf(name) === index;
            }).sort()
        };
    }

    function same(a, b) {
        return a.track === b.track && a.format === b.format &&
            a.waivers.join("\n") === b.waivers.join("\n");
    }

    function phrase(name) {
        var value = offer.getAttribute("data-" + name);
        return value === null ? "" : value;
    }

    function waiverPhrase(count) {
        if (count === 0) {
            return phrase("remember-waivers-none");
        }
        return count === 1
            ? phrase("remember-waivers-one")
            : phrase("remember-waivers-many").replace("{count}", String(count));
    }

    function dismiss() {
        offer.hidden = true;
    }

    var remembered = load();

    form.addEventListener("submit", function () {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current()));
        } catch (_error) {
            // Storage refused: the scan is submitted exactly as it would be
            // without this file.
        }
    });

    if (!remembered || !text || !apply || !forget || same(remembered, current())) {
        return;
    }

    text.textContent = phrase("remember-summary")
        .replace("{track}", optionLabel(track, remembered.track))
        .replace("{format}", optionLabel(format, remembered.format))
        .replace("{waivers}", waiverPhrase(remembered.waivers.length));
    offer.hidden = false;

    apply.addEventListener("click", function () {
        if (track) {
            track.value = remembered.track;
        }
        if (format) {
            format.value = remembered.format;
        }
        var chosen = {};
        remembered.waivers.forEach(function (name) {
            chosen[name] = true;
        });
        boxes().forEach(function (box) {
            box.checked = chosen[box.value] === true;
        });
        // A change event from a waiver box, so the count in the panel's
        // summary (app.js) sees what a click would have told it.
        var first = boxes()[0];
        if (first) {
            first.dispatchEvent(new Event("change", { bubbles: true }));
        }
        if (details && remembered.waivers.length) {
            details.open = true;
        }
        dismiss();
        var address = form.querySelector('input[name="target_url"]');
        if (address) {
            address.focus();
        }
    });

    forget.addEventListener("click", function () {
        try {
            window.localStorage.removeItem(STORAGE_KEY);
        } catch (_error) {
            // Nothing to remove, or nothing allowed to: either way it is gone
            // from the page.
        }
        dismiss();
    });
}());
