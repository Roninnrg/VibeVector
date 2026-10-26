/* Локальная инициализация Swagger UI без CDN и inline-скриптов (CSP-safe). */
(function () {
  "use strict";

  function mount() {
    if (!window.SwaggerUIBundle) return;
    window.ui = window.SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      displayRequestDuration: true,
      docExpansion: "list",
      filter: true,
      showExtensions: true,
      showCommonExtensions: true,
      tryItOutEnabled: true,
      presets: [window.SwaggerUIBundle.presets.apis],
      layout: "BaseLayout",
      requestInterceptor: function (request) {
        // Документация живёт на том же origin, что и API.
        return request;
      },
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
