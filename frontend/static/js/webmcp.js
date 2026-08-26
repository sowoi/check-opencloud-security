/*
 * Page-scoped WebMCP tools.
 *
 * Tool names, descriptions, schemas, and endpoints come from the rendered
 * page. This file supplies transport only, so the browser tools keep using
 * the same JSON API as every other client.
 */
(function () {
    "use strict";

    function problem(response, payload) {
        var detail = payload && payload.detail;
        return new Error(detail || "Request failed with status " + response.status + ".");
    }

    function jsonRequest(endpoint, options) {
        var request = options || {};
        request.headers = Object.assign({}, request.headers, {
            "Accept": "application/json"
        });
        request.credentials = "same-origin";
        request.cache = "no-store";
        return fetch(endpoint, request).then(async function (response) {
            var payload = await response.json().catch(function () {
                return null;
            });
            if (!response.ok) {
                throw problem(response, payload);
            }
            return payload;
        });
    }

    function executeFor(config) {
        if (config.action === "scan") {
            return function (input, options) {
                return jsonRequest(config.endpoint, {
                    method: "POST",
                    signal: options && options.signal,
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(input)
                });
            };
        }

        if (config.action === "status") {
            return function (input, options) {
                return jsonRequest(config.endpoint, {
                    signal: options && options.signal
                });
            };
        }

        if (config.action === "export") {
            return async function (input, options) {
                var endpoint = config.endpoint + encodeURIComponent(input.format);
                var response = await fetch(endpoint, {
                    headers: {"Accept": "application/json"},
                    credentials: "same-origin",
                    cache: "no-store",
                    signal: options && options.signal
                });
                if (!response.ok) {
                    var payload = await response.json().catch(function () {
                        return null;
                    });
                    throw problem(response, payload);
                }

                var blob = await response.blob();
                var url = URL.createObjectURL(blob);
                var link = document.createElement("a");
                link.href = url;
                link.download = "";
                link.hidden = true;
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.setTimeout(function () {
                    URL.revokeObjectURL(url);
                }, 0);

                return {
                    ok: true,
                    format: input.format,
                    bytes: blob.size,
                    contentType: response.headers.get("content-type"),
                    signature: response.headers.get("x-cos-signature")
                };
            };
        }

        throw new Error("Unknown WebMCP action: " + config.action);
    }

    function register(modelContext, tools) {
        return Promise.all(tools.map(function (config) {
            return modelContext.registerTool({
                name: config.name,
                title: config.title,
                description: config.description,
                inputSchema: config.inputSchema,
                annotations: config.annotations,
                execute: executeFor(config)
            });
        }));
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

        var registration;
        if ("modelContext" in navigator) {
            registration = register(navigator.modelContext, tools);
        } else if ("modelContext" in document) {
            registration = register(document.modelContext, tools);
        } else {
            return;
        }
        registration.catch(function (error) {
            console.error("Could not register WebMCP tools.", error);
        });
    });
}());
