/*
 * Reveals the pinned "back to top" link once the page has scrolled past one
 * viewport. The link itself needs no script - it is a plain anchor to #main,
 * and app.css already gives every browser a reduced-motion-aware smooth
 * scroll - so this file only toggles the `hidden` attribute a long page
 * would otherwise leave off forever.
 */
(function () {
    "use strict";

    var link = document.querySelector(".back-to-top");
    if (!link) {
        return;
    }

    function update() {
        link.hidden = window.scrollY < window.innerHeight;
    }

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
}());
