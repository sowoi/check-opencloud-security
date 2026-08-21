/*
 * Live state for one scan.
 *
 * The page is rendered by the server, so this script has one job: keep the
 * waiting state honest until there is something to show, then reload once.
 * Rendering the dashboard here as well would mean two implementations of the
 * same report, and the one nobody tests would be the one people read.
 *
 * The reload is a hand-off, not a hard cut: the steps settle into done, the
 * page gets a beat to say the report is ready, falls away, and only then is
 * the new document asked for. A reader who asked for reduced motion gets the
 * old immediate reload, because the beat is the animation.
 *
 * Everything it touches is addressed by the scan's own identifier, which came
 * from the URL the visitor is already on. It asks for no other scan, and
 * there is no endpoint that would let it.
 */
(function () {
    "use strict";

    var body = document.body;
    var uuid = body.getAttribute("data-scan-uuid");
    var state = body.getAttribute("data-scan-state");
    if (!uuid) {
        return;
    }

    var TERMINAL = ["completed", "failed"];
    var POLL_MS = 2000;
    var BACKOFF_MS = 15000;

    var title = document.getElementById("progress-title");
    var detail = document.getElementById("progress-detail");
    var note = document.getElementById("queue-note");
    var expiry = document.getElementById("expiry-note");
    var steps = {
        queued: document.getElementById("step-queued"),
        running: document.getElementById("step-running"),
        done: document.getElementById("step-done")
    };

    function terminal(value) {
        return TERMINAL.indexOf(value) !== -1;
    }

    function setSteps(current) {
        if (!steps.queued) {
            return;
        }
        var order = ["queued", "running", "done"];
        var index = current === "completed" || current === "failed" ? 2
            : current === "running" ? 1 : 0;
        order.forEach(function (name, position) {
            var element = steps[name];
            if (!element) {
                return;
            }
            if (current === "failed" && position === 2) {
                element.setAttribute("data-state", "failed");
            } else if (position < index) {
                element.setAttribute("data-state", "done");
            } else if (position === index) {
                element.setAttribute("data-state", current === "completed" ? "done" : "active");
            } else {
                element.removeAttribute("data-state");
            }
        });
    }

    function describeQueue(payload) {
        if (!note) {
            return;
        }
        var queue = payload.queue || {};
        if (payload.state !== "queued") {
            note.hidden = true;
            return;
        }
        note.hidden = false;
        if (queue.position && queue.position > 1) {
            note.textContent = "Scan queued. Position in line: #" + queue.position +
                " of " + queue.length + ".";
        } else if (queue.position === 1) {
            note.textContent = "Scan queued. You are next in line.";
        } else {
            note.textContent = "Waiting for a scanner worker to pick this up.";
        }
    }

    function describeState(payload) {
        if (!title || !detail) {
            return;
        }
        if (payload.state === "running") {
            title.textContent = "Scanning the instance";
            detail.textContent = "Reading what the instance publishes: version, " +
                "capabilities, certificate, headers and the endpoints it exposes " +
                "without a login.";
        } else if (payload.state === "queued") {
            title.textContent = "Waiting for a scanner worker";
            detail.textContent = "Every worker is busy right now. Your scan keeps " +
                "its place in line and starts as soon as one is free.";
        }
    }

    function countdown(seconds) {
        if (!expiry || typeof seconds !== "number" || seconds <= 0) {
            return;
        }
        var minutes = Math.max(1, Math.round(seconds / 60));
        expiry.textContent = "This page expires in about " + minutes +
            " minute" + (minutes === 1 ? "" : "s") +
            ", after which the link stops working and the result is gone.";
    }

    var delay = POLL_MS;

    /*
     * A terminal state is announced, held for a beat so the settled steps
     * register, and only then traded for the rendered page. The exit mark is
     * what app.css turns into the fall-away; without motion to show, the
     * whole sequence collapses back to the plain reload.
     */
    var reducedMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function finish(state) {
        if (reducedMotion) {
            window.location.reload();
            return;
        }
        if (title) {
            title.textContent = state === "completed"
                ? "Report ready" : "Scan finished";
        }
        if (detail) {
            detail.textContent = state === "completed"
                ? "The grade is in. Opening the report."
                : "The scan could not be completed. Opening what came back.";
        }
        window.setTimeout(function () {
            document.documentElement.setAttribute("data-exit", "true");
            window.setTimeout(function () {
                window.location.reload();
            }, 300);
        }, 1100);
    }

    function poll() {
        fetch("/api/scans/" + encodeURIComponent(uuid), {
            headers: { "Accept": "application/json" },
            credentials: "omit",
            cache: "no-store"
        }).then(function (response) {
            if (response.status === 404) {
                window.location.reload();
                return null;
            }
            if (!response.ok) {
                throw new Error("unexpected status " + response.status);
            }
            return response.json();
        }).then(function (payload) {
            if (!payload) {
                return;
            }
            delay = POLL_MS;
            setSteps(payload.state);
            describeState(payload);
            describeQueue(payload);
            countdown(payload.expiresIn);
            if (terminal(payload.state)) {
                finish(payload.state);
                return;
            }
            window.setTimeout(poll, delay);
        }).catch(function () {
            // A hiccup on the way back is not a reason to give up on a scan
            // that is probably still running; slow down instead of stopping.
            delay = Math.min(BACKOFF_MS, delay * 2);
            window.setTimeout(poll, delay);
        });
    }

    setSteps(state);
    if (!terminal(state)) {
        window.setTimeout(poll, 600);
    }
}());
