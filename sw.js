/* sw.js — Meu Tênis PWA — app shell cache + offline */
const CACHE = "meu-tenis-v2";
const SHELL = [
  "/style.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-256.png",
  "/apple-touch-icon.png",
  "/login"
];

// Instalação: pré-cache do shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

// Ativação: limpa caches antigos
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

// Util: identifica navegação de página (dados) vs estático
function isDataPage(url) {
  const path = new URL(url).pathname;
  // Páginas autenticadas com dados dinâmicos: network-first
  return ["/", "/partidas", "/treinos", "/ranking", "/torneios", "/perfil", "/login", "/logout"].some((p) => path === p || path.startsWith("/torneios/") || path.startsWith("/api/"));
}

function isStaticAsset(url) {
  const path = new URL(url).pathname;
  return path.endsWith(".css") || path.endsWith(".js") || path.endsWith(".png") || path.endsWith(".webmanifest") || path.includes("fonts.googleapis") || path.includes("fonts.gstatic") || path.includes("cdn.jsdelivr.net");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Só GET
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Ignora outros domínios exceto os estáticos listados (fonts, cdn)
  if (url.origin !== location.origin && !isStaticAsset(req.url)) return;

  // NÃO cachear login POST e logout já filtrado, e nunca cachear tentativa de login com senha
  // Para páginas de dados: network-first, cai pro cache, depois offline
  if (isDataPage(req.url)) {
    event.respondWith(
      fetch(req, { cache: "no-store", credentials: "same-origin" })
        .then((resp) => {
          // Não guarda respostas de login com erro ou redirect de auth; só guarda 200
          if (resp.ok && resp.headers.get("content-type") && resp.headers.get("content-type").includes("text/html")) {
            const clone = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(req, clone));
          }
          return resp;
        })
        .catch(() => {
          return caches.match(req).then((cached) => {
            if (cached) return cached;
            // fallback offline: se for navegação, mostra shell offline simples
            if (req.headers.get("accept") && req.headers.get("accept").includes("text/html")) {
              return caches.match("/login").then((login) => login || new Response("<!doctype html><title>Offline</title><body style=\"font-family:Inter,sans-serif;padding:24px;background:#EDF1F0;color:#10243B\"><h1>Você está offline</h1><p>Sem conexão. Tente novamente quando a rede voltar.</p><a href=\"/\">Voltar ao Painel</a>", { headers: { "Content-Type": "text/html" } }));
            }
            return new Response("Offline", { status: 503 });
          });
        })
    );
    return;
  }

  // Estáticos: cache-first
  if (isStaticAsset(req.url)) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) {
          // revalida em segundo plano
          event.waitUntil(fetch(req).then((resp) => {
            if (resp.ok) caches.open(CACHE).then((c) => c.put(req, resp));
          }).catch(()=>{}));
          return cached;
        }
        return fetch(req).then((resp) => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE).then((c) => c.put(req, clone));
          }
          return resp;
        }).catch(() => {
          return new Response("", { status: 504 });
        });
      })
    );
    return;
  }

  // Outros: network-first genérico
  event.respondWith(fetch(req).catch(() => caches.match(req)));
});
