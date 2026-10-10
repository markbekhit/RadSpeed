/* Public website page counts only. Never load this file in clinical work areas. */
(function () {
  'use strict';
  var script = document.currentScript;
  if (!script || window.__publicWebsiteAnalytics || navigator.globalPrivacyControl || navigator.doNotTrack === '1') return;
  var host = script.dataset.siteHost;
  if (location.hostname !== host) return;
  var allowed = script.dataset.publicPaths ? new RegExp(script.dataset.publicPaths) : null;
  var privatePath = /^\/(?:api|app|auth|login|logout|admin|wp-admin|wp-login\.php|account|settings|patients|score|s|reset|invite|staff|audit|submit-listing|add-listing)(?:\/|$)/;
  function publicPage() { return !privatePath.test(location.pathname) && (!allowed || allowed.test(location.pathname)); }
  if (!publicPage()) return;
  window.__publicWebsiteAnalytics = true;
  var measurement = script.dataset.gaId;
  if (measurement) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', measurement, { send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false, page_location: location.origin + location.pathname, page_referrer: (function () { try { return new URL(document.referrer).origin + "/"; } catch (_) { return ""; } })() });
    var google = document.createElement('script');
    google.async = true;
    google.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(measurement);
    document.head.appendChild(google);
    var lastPath;
    function pageView() {
      if (!publicPage() || location.pathname === lastPath) return;
      lastPath = location.pathname;
      var page = new URL(location.origin + location.pathname);
      var params = new URLSearchParams(location.search);
      ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach(function (key) {
        var value = params.get(key);
        if (value && /^[a-z0-9_-]{1,100}$/i.test(value)) page.searchParams.set(key, value);
      });
      var referrer = '';
      try { referrer = new URL(document.referrer).origin + '/'; } catch (_) {}
      window.gtag('event', 'page_view', { send_to: measurement, page_location: page.href, page_referrer: referrer, page_title: document.title });
    }
    pageView();
    ['pushState', 'replaceState'].forEach(function (method) {
      var original = history[method];
      history[method] = function () {
        var result = original.apply(this, arguments);
        setTimeout(pageView, 0);
        return result;
      };
    });
    window.addEventListener('popstate', pageView);
  }
  // Query strings outside the usual campaign tags are not sent to Cloudflare.
  var safeQuery = Array.from(new URLSearchParams(location.search)).every(function (pair) {
    return /^utm_(source|medium|campaign|content|term)$/.test(pair[0]) && /^[a-z0-9_-]{1,100}$/i.test(pair[1]);
  });
  if (script.dataset.cfToken && safeQuery && !location.hash) {
    var cloudflare = document.createElement('script');
    cloudflare.type = 'module';
    cloudflare.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    cloudflare.setAttribute('data-cf-beacon', JSON.stringify({ token: script.dataset.cfToken }));
    document.head.appendChild(cloudflare);
  }
})();
