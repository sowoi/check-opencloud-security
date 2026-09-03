/*
 * The operator's area, kept current.
 *
 * Two jobs, and both of them are enhancements over a page that already works
 * without any of this: the statistics refresh in place rather than by
 * reloading, and the audit records arrive as they are written instead of when
 * somebody presses F5. Without scripting the page still renders every
 * reading the server put in it, and the three forms are ordinary forms that
 * post and reload.
 *
 * Every sentence it writes was rendered by the server, in the language the
 * page is in, and read from a `data-` attribute. This file carries no English
 * of its own - the same rule the rest of the frontend follows.
 *
 * The audit stream is EventSource against this origin, which the policy's
 * `connect-src 'self'` allows and nothing else. It is off until asked for:
 * an operator who opened the area to press a button should not silently
 * start a long-lived connection reading the audit trail.
 *
 * One idea runs through the rest of it: **a reading that has stopped arriving
 * must not look like a reading that is not changing.** A poll swallows its
 * errors, so a dead backend and a quiet one are the same picture - hence the
 * age stamp that counts up, the tile that lights when its value moves, and
 * the dot that pulses only while a fetch is actually in flight. And the page
 * stops polling entirely while nobody is looking at it: a tab left open
 * overnight was asking for the state every ten seconds until morning.
 */
(function () {
    "use strict";

    var body = document.body;
    if (!body || body.getAttribute("data-admin") === null) {
        return;
    }

    function text(name) {
        return body.getAttribute("data-admin-" + name) || "";
    }

    function fill(template, values) {
        return template.replace(/\{(\w+)\}/g, function (whole, key) {
            return Object.prototype.hasOwnProperty.call(values, key)
                ? String(values[key])
                : whole;
        });
    }

    function put(name, value, state) {
        var node = document.querySelector('[data-value="' + name + '"]');
        if (!node) {
            return;
        }
        node.textContent = value;
        if (state) {
            node.setAttribute("data-state", state);
        } else {
            node.removeAttribute("data-state");
        }
    }

    // ------------------------------------------------------- the statistics

    // What each tile reads now, so the next paint can tell what moved. A
    // tile's signature is every reading inside it, because a queue that
    // drains while the worker count stays put is still news.
    function signature(tile) {
        return Array.prototype.map.call(
            tile.querySelectorAll("[data-value]"),
            function (node) { return node.textContent; }
        ).join("");
    }

    var tiles = document.querySelectorAll(".admin-stat");

    function flash(before) {
        Array.prototype.forEach.call(tiles, function (tile, index) {
            if (before[index] === undefined || signature(tile) === before[index]) {
                return;
            }
            tile.setAttribute("data-changed", "true");
            window.clearTimeout(tile.changedTimer);
            tile.changedTimer = window.setTimeout(function () {
                tile.removeAttribute("data-changed");
            }, 1200);
        });
    }

    var painted = false;

    function paint(stats) {
        // Taken before anything is written, and compared after. The first
        // paint is not a change - every tile goes from a placeholder to a
        // reading, and lighting all four would teach an operator to ignore
        // the one signal that says something moved.
        var before = painted
            ? Array.prototype.map.call(tiles, signature)
            : [];

        // Three answers, not two. The heartbeat this reads is a key in the
        // store, so a store that is gone takes the answer with it - and a
        // tile that called that "not answering" was telling an operator to
        // restart a worker that may be perfectly healthy. `alive` is null
        // exactly then, and the tile says which of the two outages this is.
        var worker = stats.worker || {};
        var store = stats.store || {};
        if (store.reachable === false || worker.alive === null) {
            put("worker", text("worker-unknown"), "warn");
            put("queue", text("store-down"));
        } else {
            put(
                "worker",
                worker.alive ? text("worker-up") : text("worker-down"),
                worker.alive ? "good" : "bad"
            );
            put("queue", fill(text("queue"), {
                depth: worker.queueDepth === null ? "?" : worker.queueDepth,
                workers: worker.maxWorkers
            }));
        }

        var limits = stats.limits || {};
        put("ratelimit", fill(text("ratelimit"), {
            limit: limits.ipRateLimit,
            window: limits.ipRateWindow
        }));
        put("cooldown", fill(text("cooldown"), { seconds: limits.targetCooldown }));

        // The keys the state document actually uses: `updated` is the date
        // the schedule itself carries, `advisories` is how many the database
        // holds. Both are the same names /healthz reports them under.
        var reference = stats.referenceData || {};
        var schedule = reference.releaseSchedule || {};
        var advisories = reference.advisories || {};
        put("schedule", schedule.updated || text("unknown"));
        put("schedule-checked", fill(text("checked"), {
            when: schedule.checked || text("never")
        }));
        put("advisories", String(
            advisories.advisories === undefined ? "-" : advisories.advisories
        ));
        put("advisories-checked", fill(text("checked"), {
            when: advisories.checked || text("never")
        }));

        var index = stats.searchIndex || {};
        var state = index.unreadable ? "stale" : (index.fresh ? "fresh" : "stale");
        if (!index.builtFor && !index.unreadable && index.fresh) {
            state = "unknown";
        }
        put("index-state", index.fresh ? text("index-fresh") : text("index-stale"), state);
        put("index-detail", describeIndex(index));

        flash(before);
        painted = true;
    }

    function describeIndex(index) {
        if (index.unreadable) {
            return text("index-unreadable");
        }
        if (index.builtFor && index.builtFor !== index.running) {
            return fill(text("index-release"), {
                built: index.builtFor,
                running: index.running
            });
        }
        var missing = (index.missingPaths || []).concat(index.missingLocales || []);
        if (missing.length) {
            return fill(text("index-missing"), { list: missing.join(", ") });
        }
        if ((index.changedPaths || []).length) {
            return fill(text("index-changed"), {
                count: index.changedPaths.length
            });
        }
        return text("index-ok");
    }

    // ------------------------------------------------ how old the readings are

    var interval = parseInt(body.getAttribute("data-admin-poll"), 10);
    if (!(interval > 0)) {
        interval = 0;
    }

    // When the last poll actually came back, and how far past that a reading
    // stops being "now". Three missed polls is a service that has not
    // answered for half a minute at the default interval, which is long
    // enough to mean something and short enough to be worth saying.
    var lastAnswer = null;
    var staleAfter = (interval || 10) * 3;
    var staleNote = document.getElementById("admin-stale");
    var band = document.querySelector(".admin-band");
    var inFlight = 0;

    function age() {
        if (lastAnswer === null) {
            put("age", text("age-waiting"), "stale");
            if (staleNote) {
                staleNote.hidden = true;
            }
            return;
        }
        var seconds = Math.max(0, Math.round((Date.now() - lastAnswer) / 1000));
        var stale = seconds > staleAfter;
        if (seconds < 90) {
            put("age", fill(text("age-seconds"), { seconds: seconds }),
                stale ? "stale" : null);
        } else {
            put("age", fill(text("age-minutes"), {
                minutes: Math.round(seconds / 60)
            }), "stale");
        }
        if (staleNote) {
            // Hidden and shown rather than written: the sentence is the
            // server's, and this only decides whether it is true yet.
            staleNote.hidden = !stale;
        }
    }

    function busy(active) {
        inFlight = Math.max(0, inFlight + (active ? 1 : -1));
        if (band) {
            if (inFlight) {
                band.setAttribute("data-busy", "true");
            } else {
                band.removeAttribute("data-busy");
            }
        }
    }

    function refresh() {
        busy(true);
        return window.fetch("/admin/state", {
            headers: { Accept: "application/json" },
            credentials: "same-origin"
        }).then(function (response) {
            return response.ok ? response.json() : null;
        }).then(function (stats) {
            if (stats) {
                paint(stats);
                lastAnswer = Date.now();
            }
        }).catch(function () {
            // Still not worth a message of its own: the next poll is a few
            // seconds away and the readings on screen are the last ones the
            // server really gave. What must not happen is the page going on
            // presenting them as the present tense, and that is the age
            // stamp's job rather than this one's - `lastAnswer` is simply
            // not moved, so the count keeps rising until an answer arrives.
        }).then(function () {
            busy(false);
            age();
        });
    }

    // The clock ticks whether or not a poll is in flight, so a reading that
    // is quietly getting older says so between polls and not only at one.
    window.setInterval(age, 1000);
    age();

    // ------------------------------------------------------------- the poll
    //
    // Paused while nobody is looking. A tab left open overnight asked this
    // service for its state every ten seconds until somebody came back to
    // it - eight thousand requests to answer a question nobody was reading.
    // On returning, the first thing that happens is a poll, so the page is
    // current before the operator has finished focusing on it.

    var timer = null;

    function polling(on) {
        if (!interval) {
            return;
        }
        if (on && timer === null) {
            timer = window.setInterval(refresh, interval * 1000);
        } else if (!on && timer !== null) {
            window.clearInterval(timer);
            timer = null;
        }
    }

    function visible() {
        return document.visibilityState !== "hidden";
    }

    document.addEventListener("visibilitychange", function () {
        polling(visible());
        if (visible()) {
            refresh();
        }
    });

    refresh();
    polling(visible());

    // ---------------------------------------------------------- the actions

    var outcome = document.getElementById("admin-outcome");
    var probed = document.getElementById("admin-probe");

    function said(answer) {
        if (probed) {
            probed.hidden = true;
        }
        if (outcome) {
            outcome.textContent = fill(text("outcome-" + answer.state), answer);
            outcome.setAttribute("data-outcome", answer.state);
            outcome.hidden = false;
        }
    }

    // What the dry run found, one line per source. The answer for each is a
    // word the server has a sentence for; a word it has none for is dropped
    // rather than printed, because this list is not the place to invent
    // English.
    function reported(sources) {
        if (!probed) {
            return;
        }
        if (outcome) {
            outcome.hidden = true;
        }
        probed.textContent = "";
        Object.keys(sources).forEach(function (source) {
            var label = text("probe-" + source);
            var answer = text("probe-" + sources[source]);
            if (!label || !answer) {
                return;
            }
            var item = document.createElement("li");
            item.textContent = fill(label, { answer: answer });
            item.setAttribute("data-answer", sources[source]);
            probed.appendChild(item);
        });
        probed.hidden = !probed.children.length;
    }

    function posts(form, show) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var button = form.querySelector("button");
            if (button) {
                button.disabled = true;
            }
            busy(true);
            window.fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { Accept: "application/json" },
                credentials: "same-origin"
            }).then(function (response) {
                return response.json();
            }).then(function (answer) {
                show(answer);
                refresh();
            }).catch(function () {
                // Falling back to what the page would have done anyway.
                form.submit();
            }).then(function () {
                busy(false);
                if (button) {
                    button.disabled = false;
                }
            });
        });
    }

    Array.prototype.forEach.call(
        document.querySelectorAll("[data-admin-action]"),
        function (form) { posts(form, said); }
    );

    Array.prototype.forEach.call(
        document.querySelectorAll("[data-admin-probe]"),
        function (form) {
            posts(form, function (answer) {
                // A dry run held back by its own cooldown is an ordinary
                // outcome sentence; only a run that happened has sources.
                if (answer.state === "probed") {
                    reported(answer.sources || {});
                } else {
                    said(answer);
                }
            });
        }
    );

    // -------------------------------------------------- the quiet controls

    var asked = document.querySelector("[data-admin-refresh]");
    if (asked) {
        asked.addEventListener("click", function () {
            refresh();
        });
    }

    // The readings as text, for an issue report. It asks for them again
    // rather than scraping the tiles, so what is copied is the document the
    // service answered with and not this page's rendering of it - and the
    // clipboard is the only place any of it goes.
    var copy = document.querySelector("[data-admin-copy]");
    var clipboard = navigator.clipboard;
    if (copy && clipboard && typeof clipboard.writeText === "function") {
        copy.hidden = false;
        copy.addEventListener("click", function () {
            var label = copy.textContent;
            busy(true);
            window.fetch("/admin/state", {
                headers: { Accept: "application/json" },
                credentials: "same-origin"
            }).then(function (response) {
                return response.ok ? response.text() : Promise.reject();
            }).then(function (document_) {
                return clipboard.writeText(document_);
            }).then(function () {
                answered(copy, label, "done");
            }, function () {
                answered(copy, label, "failed");
            }).then(function () {
                busy(false);
            });
        });
    }

    // Said on the button that was pressed and gone again in a moment - the
    // same answer the report page's copy buttons give.
    function answered(button, label, state) {
        button.textContent = button.getAttribute("data-admin-" + state) || label;
        button.setAttribute("data-admin-state", state);
        window.clearTimeout(button.answerTimer);
        button.answerTimer = window.setTimeout(function () {
            button.textContent = label;
            button.removeAttribute("data-admin-state");
        }, 2000);
    }

    // ----------------------------------------------------- the audit stream

    var toggle = document.querySelector("[data-audit-toggle]");
    var clear = document.querySelector("[data-audit-clear]");
    var list = document.getElementById("admin-audit-list");
    var stateLabel = document.getElementById("admin-audit-state");
    var note = document.getElementById("admin-audit-note");
    var empty = document.getElementById("admin-audit-empty");
    var stream = null;

    function say(state, label) {
        if (stateLabel) {
            stateLabel.textContent = label;
            stateLabel.setAttribute("data-state", state);
        }
    }

    // Why it stopped, when there is a why. A stream that ends because the
    // server capped it at half an hour and a stream that ends because a
    // proxy dropped it look identical from here, and only one of them means
    // "press Follow again". Passing null takes the sentence away.
    function explain(sentence) {
        if (!note) {
            return;
        }
        note.textContent = sentence || "";
        note.hidden = !sentence;
    }

    function append(line) {
        if (!list) {
            return;
        }
        var item = document.createElement("li");
        // textContent, never innerHTML: a record is a string the audit log
        // wrote from values somebody else chose, and this list is the last
        // place that should decide any of it is markup.
        item.textContent = line;
        item.setAttribute("data-fresh", "true");
        list.insertBefore(item, list.firstChild);
        window.setTimeout(function () {
            item.removeAttribute("data-fresh");
        }, 1200);
        if (empty) {
            empty.hidden = true;
        }
        // The window is bounded on the server; keeping the page bounded too
        // stops a tab left open overnight from growing without limit.
        while (list.children.length > 300) {
            list.removeChild(list.lastChild);
        }
    }

    // Closing the connection and putting the button back to "Follow",
    // without deciding what the state label should say - the caller knows
    // whether this is an operator pressing stop or the server having ended
    // it, and those are not the same sentence.
    function release() {
        if (stream) {
            stream.close();
            stream = null;
        }
        if (toggle) {
            toggle.setAttribute("aria-pressed", "false");
            toggle.textContent = text("audit-follow");
        }
    }

    function stop() {
        release();
        say("off", text("audit-off"));
        explain(null);
    }

    function start() {
        if (!window.EventSource) {
            say("unavailable", text("audit-unsupported"));
            return;
        }
        explain(null);
        stream = new window.EventSource("/admin/audit/stream");
        say("live", text("audit-live"));
        if (toggle) {
            toggle.setAttribute("aria-pressed", "true");
            toggle.textContent = text("audit-stop");
        }
        stream.addEventListener("record", function (event) {
            append(event.data);
        });
        // The server's own account of the connection, which it has been
        // sending all along and nothing was listening to. `disabled` means
        // this deployment keeps no trail, `closed` means the half-hour cap
        // was reached - and in both cases the connection is finished, so it
        // is let go rather than left for EventSource to reopen. Reopening a
        // capped stream would turn the cap into a reconnect loop, and
        // reopening a disabled one asks a question already answered.
        stream.addEventListener("state", function (event) {
            if (event.data === "disabled") {
                release();
                say("unavailable", text("audit-disabled"));
                explain(text("audit-disabled-note"));
            } else if (event.data === "closed") {
                release();
                say("off", text("audit-closed"));
                explain(text("audit-closed-note"));
            } else {
                say("live", text("audit-live"));
                explain(null);
            }
        });
        stream.addEventListener("error", function () {
            // EventSource reconnects on its own; saying so beats a silent
            // gap in a view somebody is treating as live.
            say("unavailable", text("audit-reconnecting"));
        });
        stream.addEventListener("open", function () {
            say("live", text("audit-live"));
        });
    }

    if (toggle) {
        say("off", text("audit-off"));
        toggle.addEventListener("click", function () {
            if (stream) {
                stop();
            } else {
                start();
            }
        });
    }

    // Empties the list on screen and nothing else: the records this view is
    // a window on are the server's, and the window closing is not a reason
    // for anything to be forgotten anywhere it is kept.
    if (clear) {
        clear.addEventListener("click", function () {
            if (list) {
                list.textContent = "";
            }
            if (empty) {
                empty.hidden = false;
            }
        });
    }

    // A stream is a connection the browser will otherwise keep trying to
    // hold open as the page goes away.
    window.addEventListener("pagehide", stop);
}());
