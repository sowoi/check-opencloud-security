/*
 * The search page, over an index built at release time.
 *
 * Every sentence this file can show is rendered into the markup by the
 * server, in the language the page is in, and the index it reads is named
 * there too. Nothing here is written in one language and nothing here knows
 * about a scan: the index has no result page in it, and the guard below
 * refuses a /scan/ path even if one ever appeared.
 */
(function () {
    "use strict";

    var root = document.querySelector("[data-search-root]");
    if (!root) {
        return;
    }
    var input = root.querySelector('input[name="q"]');
    var status = root.querySelector("[data-search-status]");
    var results = root.querySelector("[data-search-results]");
    var query = new URLSearchParams(window.location.search).get("q") || "";
    var base = root.getAttribute("data-search-index") || "/static/search-index.json";
    var locale = root.getAttribute("data-search-locale") || "en";
    var countLabel = root.getAttribute("data-search-results-label") || "{count}";
    var emptyLabel = root.getAttribute("data-search-empty-label") || "";
    var errorLabel = root.getAttribute("data-search-error-label") || "";
    input.value = query.slice(0, 120);

    function overlayUrl() {
        if (!locale || locale === "en" || !/^[a-z]{2}$/.test(locale)) {
            return "";
        }
        return base.replace(/\.json$/, "." + locale + ".json");
    }

    // The overlay carries the translated title, summary and - for the pages
    // this project writes by hand - the translated text. A guide generated
    // from the repository has no translated body, so it keeps the English one
    // rather than dropping out of search.
    function merge(pages, overlay) {
        var byPath = {};
        overlay.forEach(function (entry) {
            if (entry && typeof entry.path === "string") {
                byPath[entry.path] = entry;
            }
        });
        return pages.map(function (page) {
            var translated = byPath[page.path];
            if (!translated) {
                return page;
            }
            return {
                path: page.path,
                title: translated.title || page.title,
                summary: translated.summary || page.summary,
                body: translated.body || page.body
            };
        });
    }

    function words(value) {
        return value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    }

    function show(pages) {
        var terms = words(query);
        results.replaceChildren();
        if (!terms.length) {
            return;
        }
        var matches = pages.map(function (page) {
            var title = String(page.title || "").toLocaleLowerCase();
            var summary = String(page.summary || "").toLocaleLowerCase();
            var body = String(page.body || "").toLocaleLowerCase();
            if (!terms.every(function (term) {
                return title.includes(term) || summary.includes(term) || body.includes(term);
            })) {
                return null;
            }
            var score = terms.reduce(function (total, term) {
                return total + (title.includes(term) ? 8 : 0)
                    + (summary.includes(term) ? 3 : 0)
                    + (body.includes(term) ? 1 : 0);
            }, 0);
            return {page: page, score: score};
        }).filter(Boolean).sort(function (left, right) {
            return right.score - left.score || left.page.title.localeCompare(right.page.title);
        }).slice(0, 12);

        matches.forEach(function (match) {
            var page = match.page;
            if (typeof page.path !== "string" || !page.path.startsWith("/")
                    || page.path.startsWith("/scan/")) {
                return;
            }
            var item = document.createElement("li");
            var link = document.createElement("a");
            var heading = document.createElement("strong");
            var summary = document.createElement("span");
            link.href = page.path;
            heading.textContent = page.title;
            summary.textContent = page.summary;
            link.append(heading, summary);
            item.appendChild(link);
            results.appendChild(item);
        });
        status.textContent = results.children.length
            ? countLabel.replace("{count}", String(results.children.length))
            : emptyLabel;
    }

    function load(url) {
        return fetch(url, {credentials: "same-origin"}).then(function (response) {
            if (!response.ok) {
                throw new Error("index unavailable");
            }
            return response.json();
        });
    }

    load(base)
        .then(function (index) {
            var pages = Array.isArray(index.pages) ? index.pages : [];
            var overlay = overlayUrl();
            if (!overlay) {
                return pages;
            }
            // A missing translation is not a broken search: the English
            // index still answers.
            return load(overlay).then(function (translated) {
                return merge(pages, Array.isArray(translated.pages) ? translated.pages : []);
            }, function () {
                return pages;
            });
        })
        .then(show)
        .catch(function () {
            status.textContent = errorLabel;
        });
}());

