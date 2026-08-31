/*
 * The picker over the rendered configuration fragments, and the copy button.
 *
 * The server rendered every flavour into the page, each under its own
 * heading. This file's whole job is to collapse them into one visible block
 * with a picker above it - so the section stays short for the reader who has
 * scripting, and stays complete for the reader who does not. Nothing is
 * generated here: the fragments are `opencloud_local_scan.snippets`' output,
 * and rebuilding them in JavaScript would be a second implementation of the
 * one thing on this page that has to be exactly right.
 *
 * The chosen flavour is remembered in localStorage, because somebody who runs
 * Caddy runs Caddy on the next scan too, and re-picking it every time is a
 * question the page already knows the answer to. It is a convenience and
 * nothing else: every access is guarded, and a browser that refuses storage
 * gets the first flavour and a picker that works exactly as well.
 *
 * The copy button is rendered `hidden` and shown from here, the same way
 * share.js does it and for the same reason: a clipboard write needs a secure
 * context, and a button that could never work is worse than no button - the
 * fragment itself is on the page and can be selected by hand.
 */
(function () {
    "use strict";

    var card = document.getElementById("fragment-card");
    if (!card) {
        return;
    }

    var picker = card.querySelector(".flavour-picker");
    var buttons = card.querySelectorAll("[data-flavour]");
    var fragments = card.querySelectorAll("[data-fragment]");
    if (!picker || !buttons.length || !fragments.length) {
        return;
    }

    var STORAGE_KEY = "cos.fragment.flavour";

    function stored() {
        try {
            return window.localStorage.getItem(STORAGE_KEY);
        } catch (error) {
            // Private windows and blocked site data both throw on access
            // rather than answering null, so this is a catch and not a check.
            return null;
        }
    }

    function remember(value) {
        try {
            window.localStorage.setItem(STORAGE_KEY, value);
        } catch (error) {
            // A preference that cannot be saved is still a preference that
            // works for this page.
        }
    }

    function show(chosen) {
        Array.prototype.forEach.call(fragments, function (fragment) {
            fragment.hidden = fragment.getAttribute("data-fragment") !== chosen;
        });
        Array.prototype.forEach.call(buttons, function (button) {
            var mine = button.getAttribute("data-flavour") === chosen;
            button.setAttribute("aria-pressed", mine ? "true" : "false");
        });
    }

    function known(value) {
        return Array.prototype.some.call(buttons, function (button) {
            return button.getAttribute("data-flavour") === value;
        });
    }

    var initial = stored();
    if (!known(initial)) {
        initial = buttons[0].getAttribute("data-flavour");
    }

    Array.prototype.forEach.call(buttons, function (button) {
        button.addEventListener("click", function () {
            var chosen = button.getAttribute("data-flavour");
            show(chosen);
            remember(chosen);
        });
    });

    // The marker app.css hangs the per-fragment headings off: with a picker on
    // the page they repeat the pressed button, without one they are the only
    // thing separating five blocks.
    card.setAttribute("data-fragment-picked", "true");
    picker.hidden = false;
    show(initial);

    // ------------------------------------------------------------- copying
    var clipboard = navigator.clipboard;
    if (!clipboard || typeof clipboard.writeText !== "function") {
        return;
    }

    Array.prototype.forEach.call(
        card.querySelectorAll("[data-copy-fragment]"),
        function (button) {
            var fragment = card.querySelector(
                '[data-fragment="' + button.getAttribute("data-copy-fragment") + '"]'
            );
            var code = fragment ? fragment.querySelector("pre code") : null;
            if (!code) {
                return;
            }
            var label = button.textContent;
            button.hidden = false;
            button.addEventListener("click", function () {
                clipboard.writeText(code.textContent).then(
                    function () {
                        announce(button, button.getAttribute("data-copy-done"), label);
                    },
                    function () {
                        announce(button, button.getAttribute("data-copy-failed"), label);
                    }
                );
            });
        }
    );

    function announce(button, message, label) {
        button.textContent = message;
        window.clearTimeout(button.copyTimer);
        button.copyTimer = window.setTimeout(function () {
            button.textContent = label;
        }, 2000);
    }
}());
