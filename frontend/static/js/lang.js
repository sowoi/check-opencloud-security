/*
 * The language switcher, when scripting is available.
 *
 * The form works without this file: pick a language, press the button, the
 * server sets a cookie and sends the reader back to the page they were on.
 * All this does is submit on change and let the stylesheet hide the button,
 * which it only does once the document has been marked as enhanced - so with
 * scripting blocked the button stays visible and stays the way out.
 */
(function () {
    "use strict";

    var form = document.querySelector("[data-language-form]");
    if (!form) {
        return;
    }

    var select = form.querySelector("select");
    if (!select) {
        return;
    }

    document.documentElement.setAttribute("data-language", "enhanced");

    select.addEventListener("change", function () {
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    });
}());
