/*
 * The header menu on a narrow screen.
 *
 * Six links and a brand line do not fit across a phone, and a nav that
 * overflows is one that has to be scrolled sideways to be read. This file
 * collapses them behind a button - and it is the file itself that turns the
 * collapsed layout on, by marking the document, so that with scripting
 * blocked the links simply wrap onto their own row and every page stays
 * reachable.
 */
(function () {
    "use strict";

    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) {
        return;
    }

    document.documentElement.setAttribute("data-nav", "enhanced");

    function setOpen(open) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        nav.setAttribute("data-open", open ? "true" : "false");
    }

    setOpen(false);

    toggle.addEventListener("click", function () {
        setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });

    // Escape is the way out of any menu, and the focus goes back to the
    // control that opened it rather than to the top of the document.
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
            setOpen(false);
            toggle.focus();
        }
    });

    // A menu left open while the window grows would otherwise stay open as a
    // column underneath a header that has room for the row again.
    var wide = window.matchMedia("(min-width: 901px)");
    function onWidthChange(event) {
        if (event.matches) {
            setOpen(false);
        }
    }
    if (wide.addEventListener) {
        wide.addEventListener("change", onWidthChange);
    } else if (wide.addListener) {
        wide.addListener(onWidthChange);
    }
}());
