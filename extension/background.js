/**
 * FOCUS Web Guard - Background Service Worker
 * Enforces Website Whitelisting and Browser Tab Limiting.
 */

const DEFAULT_RULES = {
  max_tabs: 5,
  allowed_sites: [
    "khanacademy.org",
    "wikipedia.org",
    "youtube.com",
    "github.com",
    "google.com"
  ],
  allowed_channels: [
    "@freecodecamp",
    "@khanacademy",
    "@veritasium",
    "@3blue1brown"
  ]
};

// Initialize rules in local storage
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["focus_rules"], (res) => {
    if (!res.focus_rules) {
      chrome.storage.local.set({ focus_rules: DEFAULT_RULES });
    }
  });
  syncRulesWithDaemon();
});

// Periodic sync with local FOCUS daemon
async function syncRulesWithDaemon() {
  try {
    const response = await fetch("http://127.0.0.1:8443/api/rules", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      if (data && data.allowed_sites) {
        chrome.storage.local.set({ focus_rules: data });
        console.log("[FOCUS Extension] Synchronized rules from local daemon:", data);
      }
    }
  } catch (err) {
    // Daemon might be offline; fallback to cached storage rules
    console.debug("[FOCUS Extension] Daemon sync skipped (daemon offline or loading).");
  }
}

// Sync rules every 15 seconds
setInterval(syncRulesWithDaemon, 15000);

// --- 1. Browser Tab Limiter ---
chrome.tabs.onCreated.addListener(async (newTab) => {
  chrome.storage.local.get(["focus_rules"], async (res) => {
    const rules = res.focus_rules || DEFAULT_RULES;
    const maxTabs = rules.max_tabs || 5;

    // Count all active tabs across all windows
    chrome.tabs.query({}, (tabs) => {
      if (tabs.length > maxTabs) {
        console.warn(`[FOCUS Extension] Max tab limit (${maxTabs}) exceeded! Closing tab: ${newTab.id}`);
        if (newTab.id) {
          chrome.tabs.remove(newTab.id);
        }
      }
    });
  });
});

// --- 2. Website Whitelist Filter ---
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  // Only inspect top-level frame navigation
  if (details.frameId !== 0) return;

  const urlStr = details.url;
  if (!urlStr) return;

  // Ignore internal browser schemes
  if (
    urlStr.startsWith("chrome://") ||
    urlStr.startsWith("chrome-extension://") ||
    urlStr.startsWith("edge://") ||
    urlStr.startsWith("about:")
  ) {
    return;
  }

  let hostname = "";
  try {
    hostname = new URL(urlStr).hostname.toLowerCase();
  } catch (e) {
    return;
  }

  chrome.storage.local.get(["focus_rules"], (res) => {
    const rules = res.focus_rules || DEFAULT_RULES;
    const allowedSites = rules.allowed_sites || [];

    // Check if hostname matches or ends with an allowed domain
    const isAllowed = allowedSites.some((site) => {
      const cleanSite = site.trim().toLowerCase();
      return hostname === cleanSite || hostname.endsWith("." + cleanSite);
    });

    if (!isAllowed) {
      console.warn(`[FOCUS Extension] Blocked non-whitelisted site: ${hostname}`);
      const blockedPageUrl = chrome.runtime.getURL("blocked.html") + "?url=" + encodeURIComponent(urlStr);
      chrome.tabs.update(details.tabId, { url: blockedPageUrl });
    }
  });
});
