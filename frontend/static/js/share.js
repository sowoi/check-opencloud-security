/*
 * The two copy buttons on a report page.
 *
 * Everything here happens in the reader's own browser. There is no request to
 * this service and none to anybody else: the text is already in the page, and
 * the clipboard is the only place it goes. The email link beside these buttons
 * needs no script at all - a `mailto:` is handed to whatever mail client the
 * reader already has - which is why it is a plain anchor in the template and
 * is not touched from here.
 *
 * The buttons are rendered `hidden` and shown from here, rather than rendered
 * visible and disabled on failure. A clipboard write needs a secure context,
 * so on plain http (or in a browser that withholds the API) the button could
 * never work, and offering a control that does nothing is worse than not
 * offering it: the template's fallback paragraph shows the address itself,
 * which needs no permission and no script. Only when the API is actually
 * present do the buttons appear and that paragraph go away.
 */
(function () {
    "use strict";

    var section = document.querySelector("[data-share-summary-text]");
    if (!section) {
        return;
    }

    // Not `navigator.clipboard &&` alone: the object exists in some insecure
    // contexts with writeText missing, which would fail at the first click
    // rather than at load, after the fallback had already been taken away.
    var clipboard = navigator.clipboard;
    if (!clipboard || typeof clipboard.writeText !== "function") {
        return;
    }

    var sources = {
        link: document.querySelector("[data-share-link-text]"),
        summary: document.querySelector("[data-share-summary-text]")
    };
    var buttons = document.querySelectorAll("[data-share-copy]");
    if (!buttons.length) {
        return;
    }

    function restore(button, label) {
        return function () {
            button.textContent = label;
            button.removeAttribute("data-share-state");
        };
    }

    function announce(button, label, state) {
        var original = button.getAttribute("data-share-label");
        if (original === null) {
            original = button.textContent;
            button.setAttribute("data-share-label", original);
        }
        button.textContent = label;
        button.setAttribute("data-share-state", state);
        window.clearTimeout(button.shareTimer);
        button.shareTimer = window.setTimeout(restore(button, original), 2000);
    }

    Array.prototype.forEach.call(buttons, function (button) {
        var source = sources[button.getAttribute("data-share-copy")];
        if (!source) {
            return;
        }
        button.hidden = false;
        button.addEventListener("click", function () {
            // `textContent` rather than innerHTML: the summary is the
            // instance's own words in places, and it goes to the clipboard as
            // text either way.
            clipboard.writeText(source.textContent.trim()).then(
                function () {
                    announce(button, button.getAttribute("data-share-done"), "done");
                },
                function () {
                    announce(button, button.getAttribute("data-share-failed"), "failed");
                }
            );
        });
    });

    var fallback = document.querySelector("[data-share-fallback]");
    if (fallback) {
        fallback.hidden = true;
    }
}());
