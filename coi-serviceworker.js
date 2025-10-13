// coi-serviceworker.js
// Enable Cross-Origin Isolation on GitHub Pages / static hosts.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Workaround for Chrome bug with cross-origin "only-if-cached"
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        // clone headers and inject COOP/COEP
        const newHeaders = new Headers(res.headers);
        newHeaders.set("Cross-Origin-Opener-Policy", "same-origin");
        newHeaders.set("Cross-Origin-Embedder-Policy", "require-corp");
        return new Response(res.body, {
          status: res.status,
          statusText: res.statusText,
          headers: newHeaders,
        });
      })
      .catch(() => fetch(req))
  );
});
