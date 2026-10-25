/**
 * FOCUS Web Guard - Background Service Worker
 * Enforces Website Whitelisting and Browser Tab Limiting.
 */

const DEFAULT_RULES = {
  max_tabs: 1,
  min_tabs: 1,
  max_tabs_range: 15,
  allowed_sites: [
    "wikipedia.org",
    "youtube.com",
    "github.com",
    "google.com"
  ],
  allowed_channels: [],
  allowed_videos: []
};

// Initialize rules in local storage
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["focus_rules"], (res) => {
    if (chrome.runtime?.lastError) return;
    if (!res || !res.focus_rules) {
      chrome.storage.local.set({ focus_rules: DEFAULT_RULES });
    }
  });
  syncRulesWithDaemon();
});

let _lastDaemonVersion = null;

// Periodic sync with local FOCUS daemon
async function syncRulesWithDaemon() {
  try {
    const response = await fetch("http://127.0.0.1:8443/api/rules", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      if (data && data.allowed_sites) {
        chrome.storage.local.set({ focus_rules: data });
        console.log("[FOCUS Extension] Synchronized rules from local daemon:", data);

        // Auto-reload extension code if daemon restarted with new updates
        if (data.daemon_version) {
          if (_lastDaemonVersion && _lastDaemonVersion !== data.daemon_version) {
            console.log("[FOCUS Extension] New daemon version detected — reloading extension code automatically!");
            _lastDaemonVersion = data.daemon_version;
            try {
              chrome.runtime.reload();
              return;
            } catch (reloadErr) { }
          }
          _lastDaemonVersion = data.daemon_version;
        }
      }
    }
  } catch (err) {
    // Daemon might be offline; fallback to cached storage rules
    console.debug("[FOCUS Extension] Daemon sync skipped (daemon offline or loading).");
  }
}

// Sync rules every 3 seconds for instant response
setInterval(syncRulesWithDaemon, 3000);

// --- 1. Browser Tab Limiter ---
chrome.tabs.onCreated.addListener((newTab) => {
  chrome.storage.local.get(["focus_rules"], (res) => {
    if (chrome.runtime?.lastError) return;
    const rules = (res && res.focus_rules) || DEFAULT_RULES;

    // When Focus Mode is OFF: all tab limits are removed (open any number of tabs)
    if (!rules.focus_mode) return;

    const maxTabs = (typeof rules.max_tabs === "number" && rules.max_tabs >= 1) ? rules.max_tabs : 1;

    // Count all active tabs across all windows
    chrome.tabs.query({}, (tabs) => {
      if (tabs && tabs.length > maxTabs && newTab && newTab.id) {
        console.warn(`[FOCUS Extension] Max tab limit (${maxTabs}) exceeded! Closing tab: ${newTab.id}`);
        chrome.tabs.remove(newTab.id).catch(() => { });
      }
    });
  });
});

// --- 2. Website Whitelist Filter ---
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  // Only inspect top-level frame navigation
  if (details.frameId !== 0 || details.tabId < 0) return;

  const urlStr = details.url;
  if (!urlStr) return;

  // Ignore internal browser schemes, extension pages, and the blocked page itself
  if (
    urlStr.startsWith("chrome://") ||
    urlStr.startsWith("chrome-extension://") ||
    urlStr.startsWith("extension://") ||
    urlStr.startsWith("edge://") ||
    urlStr.startsWith("edge-extension://") ||
    urlStr.startsWith("about:") ||
    urlStr.startsWith("blob:") ||
    urlStr.startsWith("data:") ||
    urlStr.includes("blocked.html")
  ) {
    return;
  }

  let hostname = "";
  try {
    hostname = new URL(urlStr).hostname.toLowerCase();
  } catch (e) {
    return;
  }

  // Allow local parent dashboard access
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return;
  }

  chrome.storage.local.get(["focus_rules"], (res) => {
    if (chrome.runtime?.lastError) return;
    const rules = (res && res.focus_rules) || DEFAULT_RULES;

    // When Focus Mode is OFF: all websites are 100% visible and unblocked
    if (!rules.focus_mode) return;

    const allowedSites = rules.allowed_sites || [];

    // Check if hostname matches or ends with an allowed domain
    const isAllowed = allowedSites.some((site) => {
      const cleanSite = site.trim().toLowerCase();
      return hostname === cleanSite || hostname.endsWith("." + cleanSite);
    });

    if (!isAllowed) {
      console.warn(`[FOCUS Extension] Blocked non-whitelisted site: ${hostname}`);
      const blockedPageUrl = chrome.runtime.getURL("blocked.html") + "?url=" + encodeURIComponent(urlStr);
      chrome.tabs.update(details.tabId, { url: blockedPageUrl }).catch(() => { });
    }
  });
});
