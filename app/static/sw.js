// Service Worker for offline resilience on mobile
// (plan/07-troubleshooting-backlog.md#b-6). Deliberately keeps only the
// most recently opened paper cached: reader.js decides what to cache (and
// evicts the previous paper's cache first) when a paper page finishes
// loading on a mobile viewport. This file only needs to know the shared
// cache name and how to serve from it when offline -- it never writes to
// the cache itself.
//
// Registered at the root scope (served from /sw.js via a dedicated route
// in app/main.py, not /static/sw.js) so it can intercept /papers/*
// requests, not just /static/* ones.
const CACHE_NAME = "current-offline-paper";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Every time this file's own bytes change (i.e. every real deploy), the
  // browser treats it as a new worker version and runs this -- clearing
  // the cache here is what prevents a stale cached page/JS/CSS from
  // outliving an app update instead of ever refreshing.
  event.waitUntil(caches.delete(CACHE_NAME).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const isPaperPage = /^\/papers\/[^/]+$/.test(url.pathname);
  const isCacheableAsset = url.pathname.startsWith("/static/") || /^\/papers\/[^/]+\/figures\//.test(url.pathname);

  if (isPaperPage) {
    // network-first: prefer the live version (annotations/content may
    // have changed since the page was cached); fall back to cache only
    // when the network is actually unavailable.
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }

  if (isCacheableAsset) {
    // cache-first: figures and static assets are immutable once generated.
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
  }
});
