/*
 * The arrival of things below the fold.
 *
 * Same contract as nav.js: it is the file itself that turns the behaviour
 * on, by marking the document, so a browser that never runs it simply shows
 * everything - the stylesheet hides nothing until this attribute is set.
 * The motion itself lives in app.css, where the reduced-motion reset can
 * reach it; this script only says *when* each block has arrived.
 */
(function () {
    "use strict";

    var marked = document.querySelectorAll("[data-reveal]");
    if (!marked.length) {
        return;
    }

    // No observer, no hiding: an old browser gets the page as it was.
    if (!("IntersectionObserver" in window)) {
        return;
    }

    document.documentElement.setAttribute("data-reveal-root", "on");

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.setAttribute("data-revealed", "true");
                observer.unobserve(entry.target);
            }
        });
    }, { rootMargin: "0px 0px -8% 0px" });

    marked.forEach(function (element) {
        observer.observe(element);
    });
}());
