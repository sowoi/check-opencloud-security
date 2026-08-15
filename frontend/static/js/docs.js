// Swagger UI is normally started by an inline script. This service serves a
// strict Content-Security-Policy without 'unsafe-inline' for scripts, which
// blocked that script and left the page blank, so the same call lives here
// instead and reads its one parameter from the markup.
(function () {
  "use strict";
  var mount = document.getElementById("swagger-ui");
  if (!mount || typeof window.SwaggerUIBundle !== "function") {
    return;
  }
  window.SwaggerUIBundle({
    url: mount.dataset.openapiUrl || "/openapi.json",
    dom_id: "#swagger-ui",
    layout: "BaseLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    presets: [window.SwaggerUIBundle.presets.apis],
  });
})();
