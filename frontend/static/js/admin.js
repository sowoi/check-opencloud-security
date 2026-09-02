/*
 * The operator's area, kept current.
 *
 * Two jobs, and both of them are enhancements over a page that already works
 * without any of this: the statistics refresh in place rather than by
 * reloading, and the audit records arrive as they are written instead of when
 * somebody presses F5. Without scripting the page still renders every
 * reading the server put in it, and the two refresh buttons are ordinary
 * forms that post and reload.
 *
 * Every sentence it writes was rendered by the server, in the language the
 * page is in, and read from a `data-` attribute. This file carries no English
 * of its own - the same rule the rest of the frontend follows.
 *
 * The audit stream is EventSource against this origin, which the policy's
 * `connect-src 'self'` allows and nothing else. It is off until asked for:
 * an operator who opened the area to press a button should not silently
 * start a long-lived connection reading the audit trail.
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

    function paint(stats) {
        var worker = stats.worker || {};
        put(
            "worker",
            worker.alive ? text("worker-up") : text("worker-down"),
            worker.alive ? "good" : "bad"
        );
        put("queue", fill(text("queue"), {
            depth: worker.queueDepth === null ? "?" : worker.queueDepth,
            workers: worker.maxWorkers
        }));

        var limits = stats.limits || {};
        put("ratelimit", fill(text("ratelimit"), {
            limit: limits.ipRateLimit,
            window: limits.ipRateWindow
        }));
        put("cooldown", fill(text("cooldown"), { seconds: limits.targetCooldown }));

        var reference = stats.referenceData || {};
        var schedule = reference.releaseSchedule || {};
        var advisories = reference.advisories || {};
        put("schedule", schedule.generated || text("unknown"));
        put("schedule-checked", fill(text("checked"), {
            when: schedule.checked || text("never")
        }));
        put("advisories", String(advisories.count === undefined ? "-" : advisories.count));
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

    function refresh() {
        window.fetch("/admin/state", {
            headers: { Accept: "application/json" },
            credentials: "same-origin"
        }).then(function (response) {
            return response.ok ? response.json() : null;
        }).then(function (stats) {
            if (stats) {
                paint(stats);
            }
        }).catch(function () {
            // A failed poll is not worth a message: the next one is a few
            // seconds away, and the readings on screen are still the last
            // ones the server actually gave.
        });
    }

    refresh();
    var interval = parseInt(body.getAttribute("data-admin-poll"), 10);
    if (interval > 0) {
        window.setInterval(refresh, interval * 1000);
    }

    // ---------------------------------------------------------- the actions

    var outcome = document.getElementById("admin-outcome");

    Array.prototype.forEach.call(
        document.querySelectorAll("[data-admin-action]"),
        function (form) {
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                var button = form.querySelector("button");
                if (button) {
                    button.disabled = true;
                }
                window.fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    headers: { Accept: "application/json" },
                    credentials: "same-origin"
                }).then(function (response) {
                    return response.json();
                }).then(function (answer) {
                    if (outcome) {
                        outcome.textContent = fill(
                            text("outcome-" + answer.state),
                            answer
                        );
                        outcome.setAttribute("data-outcome", answer.state);
                        outcome.hidden = false;
                    }
                    refresh();
                }).catch(function () {
                    // Falling back to what the page would have done anyway.
                    form.submit();
                }).then(function () {
                    if (button) {
                        button.disabled = false;
                    }
                });
            });
        }
    );

    // ----------------------------------------------------- the audit stream

    var toggle = document.querySelector("[data-audit-toggle]");
    var list = document.getElementById("admin-audit-list");
    var stateLabel = document.getElementById("admin-audit-state");
    var empty = document.getElementById("admin-audit-empty");
    var stream = null;

    function say(state, label) {
        if (stateLabel) {
            stateLabel.textContent = label;
            stateLabel.setAttribute("data-state", state);
        }
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

    function stop() {
        if (stream) {
            stream.close();
            stream = null;
        }
        say("off", text("audit-off"));
        if (toggle) {
            toggle.setAttribute("aria-pressed", "false");
            toggle.textContent = text("audit-follow");
        }
    }

    function start() {
        if (!window.EventSource) {
            say("unavailable", text("audit-unsupported"));
            return;
        }
        stream = new window.EventSource("/admin/audit/stream");
        say("live", text("audit-live"));
        if (toggle) {
            toggle.setAttribute("aria-pressed", "true");
            toggle.textContent = text("audit-stop");
        }
        stream.addEventListener("record", function (event) {
            append(event.data);
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

    // A stream is a connection the browser will otherwise keep trying to
    // hold open as the page goes away.
    window.addEventListener("pagehide", stop);
}());
