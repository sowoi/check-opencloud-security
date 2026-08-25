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
            // A jump - an anchor, End, a restored scroll position - can carry
            // a block past the viewport between two frames, so it never
            // intersects. Anything already above the fold has arrived too.
            if (entry.isIntersecting || entry.boundingClientRect.bottom < 0) {
                entry.target.setAttribute("data-revealed", "true");
                observer.unobserve(entry.target);
            }
        });
    }, { rootMargin: "0px 0px -8% 0px" });

    var pending = [];
    marked.forEach(function (element) {
        pending.push(element);
        observer.observe(element);
    });

    /*
     * A jump - an anchor, the End key, a scroll position the browser
     * restores - can carry a block from below the fold to above it between
     * two frames. The observer sees no crossing and the block would stay
     * hidden for good, so a scrolled page also sweeps up whatever it has
     * already passed.
     */
    function sweep() {
        pending = pending.filter(function (element) {
            if (element.getAttribute("data-revealed") === "true") {
                return false;
            }
            if (element.getBoundingClientRect().bottom >= 0) {
                return true;
            }
            element.setAttribute("data-revealed", "true");
            observer.unobserve(element);
            return false;
        });
        if (!pending.length) {
            window.removeEventListener("scroll", schedule);
        }
    }

    var queued = false;
    function schedule() {
        if (queued) {
            return;
        }
        queued = true;
        window.requestAnimationFrame(function () {
            queued = false;
            sweep();
        });
    }

    window.addEventListener("scroll", schedule, { passive: true });
}());
