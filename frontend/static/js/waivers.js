/*
 * Narrowing the list of checks that can be waived.
 *
 * The catalogue is complete on purpose - every check the scanner runs is
 * offered - and complete is exactly what makes it long. Somebody opening it
 * usually has one identifier in mind, from a report they are looking at, and
 * this lets them type it instead of hunting for it.
 *
 * It only ever sets `hidden`. Nothing is removed, nothing is reordered, and a
 * box that was ticked before the search stays ticked while it is out of
 * sight - the form still submits it, because a filter is a way of looking at
 * the list, not a second way of choosing from it.
 *
 * The field itself is revealed from here, so a reader without scripting is
 * never shown a search box that cannot search. The comparison is done against
 * the identifier and title the server already wrote into each row, folded to
 * lower case there, so this file does no translating of its own.
 */
(function () {
    "use strict";

    var field = document.querySelector("[data-waiver-filter]");
    if (!field) {
        return;
    }

    var groups = document.querySelectorAll("[data-waiver-group]");
    var options = document.querySelectorAll("[data-waiver-option]");
    var empty = document.getElementById("waiver-empty");
    if (!groups.length || !options.length) {
        return;
    }

    document.documentElement.setAttribute("data-waiver-search", "true");

    function each(nodes, visit) {
        Array.prototype.forEach.call(nodes, visit);
    }

    function filter() {
        var query = field.value.trim().toLowerCase();
        var matches = 0;

        each(options, function (option) {
            var haystack = option.getAttribute("data-waiver-option") || "";
            var hit = query === "" || haystack.indexOf(query) !== -1;
            option.hidden = !hit;
            if (hit) {
                matches += 1;
            }
        });

        // A heading over nothing is a heading that lies about what is under
        // it, so a group goes when its last entry does.
        each(groups, function (group) {
            var visible = group.querySelectorAll("[data-waiver-option]:not([hidden])");
            group.hidden = visible.length === 0;
        });

        if (empty) {
            empty.hidden = matches !== 0;
        }
    }

    field.addEventListener("input", filter);
    // A search field's own clear button fires `search`, not `input`, in some
    // browsers; without this the list would stay narrowed after it was
    // emptied.
    field.addEventListener("search", filter);
}());
