/* Only app assets are cached. NEVER cache authenticated pages, files, photos, API or POST responses. */
const CACHE='pc-static-v040';
const ASSETS=['/static/styles.css','/static/mobile.js','/static/icon-192.png','/static/icon-512.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const req=event.request;
 if(req.method!=='GET'||new URL(req.url).origin!==self.location.origin)return;
 const path=new URL(req.url).pathname;
 if(!ASSETS.includes(path))return; // sensitive content is ALWAYS network-only
 event.respondWith(caches.match(req).then(found=>found||fetch(req)));
});