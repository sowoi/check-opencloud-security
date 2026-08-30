/*
 * Reveals the pinned "back to top" link once the page has scrolled past one
 * viewport. The link itself needs no script - it is a plain anchor to #main,
 * and app.css already gives every browser a reduced-motion-aware smooth
 * scroll - so this file only toggles the `hidden` attribute a long page
 * would otherwise leave off forever.
 *
 * The one-viewport threshold is measured once rather than read live from
 * `window.innerHeight` on every scroll: on a phone, scrolling collapses the
 * browser's own address bar, which grows `innerHeight` in the middle of the
 * same gesture that grows `scrollY`. Chasing that moving target can keep the
 * link hidden well past the intended one screen of scrolling.
 */
(function () {
    "use strict";

    var link = document.querySelector(".back-to-top");
    if (!link) {
        return;
    }

    var threshold = window.innerHeight;

    function update() {
        link.hidden = window.scrollY < threshold;
    }

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", function () {
        threshold = window.innerHeight;
        update();
    });
}());
