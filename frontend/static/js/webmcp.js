/*
 * Page-scoped WebMCP tools.
 *
 * Tool names, descriptions, schemas, and endpoints come from the rendered
 * page. This file supplies transport only, so the browser tools keep using
 * the same JSON API as every other client.
 *
 * Failures are returned, never thrown. The server-side tools answer
 * `ok: false` with a status and a retryable flag so that an agent meeting a
 * per-target cooldown waits the advertised number of seconds instead of
 * retrying immediately; a browser tool that threw a bare Error would drop
 * the status, the Retry-After and the distinction between "wait" and "stop",
 * which is exactly the loop the server side was written to prevent.
 */
(function () {
    "use strict";

    /* Which answers may be repeated is the workflow layer's decision, not
     * this file's. It arrives rendered into the page beside the schema, so
     * there is no second copy of it here to drift. */
    function failure(response, payload, retry) {
        var policy = retry || {};
        var statuses = policy.retryableStatuses || [];
        var notFinished = response.status === policy.notFinishedStatus;
        var detail = payload && (payload.detail || payload.error);
        var answer = {
            ok: false,
            status: response.status,
            error: detail || "Request failed with status " + response.status + ".",
            retryable: notFinished || statuses.indexOf(response.status) !== -1
        };
        /* 409 is "right call, wrong moment": the scan exists and has not
         * finished. Saying so keeps an agent from reporting it as the 404
         * that means the scan is gone. */
        if (notFinished) {
            answer.state = (payload && payload.state) || "running";
            answer.retryAfter = policy.notFinishedRetrySeconds;
            return answer;
        }
        var retryAfter = parseInt(response.headers.get("retry-after"), 10);
        if (!Number.isNaN(retryAfter)) {
            answer.retryAfter = retryAfter;
        } else if (answer.retryable && policy.fallbackRetrySeconds) {
            answer.retryAfter = policy.fallbackRetrySeconds;
        }
        /* The API points a visitor whose own instance cannot be reached from
         * here at running the scanner themselves. An agent should relay that
         * rather than reporting an unexplained refusal. */
        if (payload && payload.hint) {
            answer.hint = payload.hint;
        }
        if (payload && payload.selfHostUrl) {
            answer.selfHostUrl = payload.selfHostUrl;
        }
        return answer;
    }

    /* A request that never reached the service: offline, DNS, a navigation
     * that aborted it. Worth retrying, and never a reason to throw. */
    function unreachable(error) {
        if (error && error.name === "AbortError") {
            return {ok: false, status: 0, error: "The call was cancelled.", retryable: false};
        }
        return {
            ok: false,
            status: 0,
            error: "Could not reach the service: " + ((error && error.message) || error),
            retryable: true
        };
    }

    function send(endpoint, options) {
        var request = Object.assign({}, options);
        request.headers = Object.assign({}, request.headers, {
            "Accept": "application/json"
        });
        request.credentials = "same-origin";
        request.cache = "no-store";
        return fetch(endpoint, request);
    }

    async function jsonRequest(endpoint, options, retry) {
        var response;
        try {
            response = await send(endpoint, options);
        } catch (error) {
            return unreachable(error);
        }
        var payload = await response.json().catch(function () {
            return null;
        });
        if (!response.ok) {
            return failure(response, payload, retry);
        }
        return payload;
    }

    function executeFor(config) {
        if (config.action === "scan") {
            return function (input, options) {
                return jsonRequest(config.endpoint, {
                    method: "POST",
                    signal: options && options.signal,
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(input)
                }, config.retry);
            };
        }

        if (config.action === "status") {
            return function (_input, options) {
                return jsonRequest(config.endpoint, {
                    signal: options && options.signal
                }, config.retry);
            };
        }

        if (config.action === "export") {
            return async function (input, options) {
                var endpoint = config.endpoint + encodeURIComponent(input.format);
                var response;
                try {
                    response = await send(endpoint, {signal: options && options.signal});
                } catch (error) {
                    return unreachable(error);
                }
                if (!response.ok) {
                    var payload = await response.json().catch(function () {
                        return null;
                    });
                    return failure(response, payload, config.retry);
                }

                var blob = await response.blob();
                var url = URL.createObjectURL(blob);
                var link = document.createElement("a");
                link.href = url;
                /* Empty: the filename comes from Content-Disposition, which
                 * is where the service already decided what a scan is called. */
                link.download = "";
                link.hidden = true;
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.setTimeout(function () {
                    URL.revokeObjectURL(url);
                }, 0);

                var answer = {
                    ok: true,
                    format: input.format,
                    bytes: blob.size,
                    contentType: response.headers.get("content-type"),
                    signature: response.headers.get("x-cos-signature"),
                    url: endpoint,
                    downloaded: true
                };

                /* A download alone leaves the agent with a file it cannot
                 * read. The text formats are the ones it can act on, so they
                 * come back as content too; a PDF is reported as its size,
                 * because a model cannot read one. */
                if (input.format !== "pdf") {
                    var limit = config.contentLimit;
                    var text = await blob.text();
                    if (limit && text.length > limit) {
                        answer.truncated = true;
                        answer.note = "The export is larger than this tool returns inline. "
                            + "Fetch " + endpoint + " for the whole document rather than "
                            + "reporting this as complete.";
                        text = text.slice(0, limit);
                    }
                    answer.content = text;
                }

                return answer;
            };
        }

        throw new Error("Unknown WebMCP action: " + config.action);
    }

    function definition(config) {
        return {
            name: config.name,
            title: config.title,
            description: config.description,
            inputSchema: config.inputSchema,
            annotations: config.annotations,
            execute: executeFor(config)
        };
    }

    function register(modelContext, tools) {
        var defined;
        try {
            defined = tools.map(definition);
        } catch (error) {
            console.error("Could not build WebMCP tool definitions.", error);
            return;
        }

        /* Two shapes of the same draft. `provideContext` declares the page's
         * whole tool set at once; `registerTool` adds them one at a time.
         * Where both exist the declarative one is used, because it states
         * what this page offers rather than accumulating it. */
        if (typeof modelContext.provideContext === "function") {
            Promise.resolve(modelContext.provideContext({tools: defined})).catch(
                function (error) {
                    console.error("Could not provide WebMCP tools.", error);
                }
            );
            return;
        }

        if (typeof modelContext.registerTool !== "function") {
            return;
        }

        /* allSettled, not all: one tool the browser rejects must not take the
         * page's other tools down with it. */
        Promise.allSettled(
            defined.map(function (tool) {
                return modelContext.registerTool(tool);
            })
        ).then(function (results) {
            results.forEach(function (result, index) {
                if (result.status === "rejected") {
                    console.error(
                        "Could not register WebMCP tool " + defined[index].name + ".",
                        result.reason
                    );
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var element = document.getElementById("webmcp-config");
        if (!element) {
            return;
        }

        var tools;
        try {
            tools = JSON.parse(element.getAttribute("data-tools") || "[]");
        } catch (error) {
            console.error("Could not read WebMCP tool definitions.", error);
            return;
        }
        if (!tools.length) {
            return;
        }

        if ("modelContext" in navigator) {
            register(navigator.modelContext, tools);
        } else if ("modelContext" in document) {
            register(document.modelContext, tools);
        }
    });
}());
