/**
 * FOCUS Parent Dashboard Client
 * Real-time REST & Firebase Cloud sync, authentication, and system control.
 */

const API_BASE = window.location.origin;
let authToken = localStorage.getItem("focus_parent_token") || "";
let fbUrl = localStorage.getItem("focus_fb_url") || "";
let fbSecret = localStorage.getItem("focus_fb_secret") || "";
let selectedDurationMins = 0;
let currentRules = { allowed_sites: [], allowed_channels: [], allowed_videos: [] };
let lastFocusToggleTime = 0;
let lastKeylockToggleTime = 0;
let lastTabChangeTime = 0;

// Reconnect tracking — when the PC goes offline then comes back, we freeze
// toggle updates briefly (3s) so initial startup sync doesn't flip switches.
let _pcWasOffline = false;
let _lastOnlineTime = 0;
const RECONNECT_FREEZE_MS = 3000; // 3s interaction debounce

// DOM Elements
const loginModal = document.getElementById("login-modal");
const appContainer = document.getElementById("app-container");
const loginForm = document.getElementById("login-form");
const pinInput = document.getElementById("pin-input");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const loginCloudBtn = document.getElementById("login-cloud-btn");
const loginCloudBtnText = document.getElementById("login-cloud-btn-text");
const loginSubtitle = document.getElementById("login-subtitle");

const cloudModal = document.getElementById("cloud-modal");
const cloudCfgBtn = document.getElementById("cloud-cfg-btn");
const cfgFbUrl = document.getElementById("cfg-fb-url");
const cfgFbSecret = document.getElementById("cfg-fb-secret");
const saveCloudBtn = document.getElementById("save-cloud-btn");
const closeCloudBtn = document.getElementById("close-cloud-btn");

const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");

const toggleFocus = document.getElementById("toggle-focus");
const focusStatusBadge = document.getElementById("focus-status-badge");
const toggleKeylock = document.getElementById("toggle-keylock");

const tabSlider = document.getElementById("tab-slider");
const tabSliderVal = document.getElementById("tab-slider-val");
const tabCountBadge = document.getElementById("tab-count-badge");
const cfgMinTabs = document.getElementById("cfg-min-tabs");
const cfgMaxTabsRange = document.getElementById("cfg-max-tabs-range");
const btnDecMinTabs = document.getElementById("btn-dec-min-tabs");
const btnIncMinTabs = document.getElementById("btn-inc-min-tabs");
const btnDecMaxTabs = document.getElementById("btn-dec-max-tabs");
const btnIncMaxTabs = document.getElementById("btn-inc-max-tabs");
const tabSliderMinLabel = document.getElementById("tab-slider-min-label");
const tabSliderMaxLabel = document.getElementById("tab-slider-max-label");

const activeAppName = document.getElementById("active-app-name");
const activeWindowTitle = document.getElementById("active-window-title");
const refreshScreenBtn = document.getElementById("refresh-screen-btn");
const screenshotContainer = document.getElementById("screenshot-container");
const screenshotImg = document.getElementById("screenshot-img");

// Section 5: Access Requests DOM Elements
const pendingRequestsBadge = document.getElementById("pending-requests-badge");
const requestsListContainer = document.getElementById("requests-list-container");
const noRequestsPlaceholder = document.getElementById("no-requests-placeholder");


// --- 1. Cloud & API Helper ---
function updateCloudModeIndicator() {
  const isCloudHost = window.location.hostname.includes("github.io") || !!fbUrl;
  if (fbUrl && fbSecret) {
    if (loginCloudBtnText) loginCloudBtnText.textContent = "Firebase Cloud: Linked 🟢 (Tap to edit)";
    if (loginSubtitle) loginSubtitle.innerHTML = "Cloud Remote Mode &bull; Enter Master PIN";
  } else if (isCloudHost) {
    if (loginCloudBtnText) loginCloudBtnText.textContent = "⚙️ Configure Firebase Cloud (Required on GitHub Pages)";
    if (loginSubtitle) loginSubtitle.innerHTML = "<span style='color: #f59e0b;'>⚠️ Tap Cloud Setup Below to Connect</span>";
  } else {
    if (loginCloudBtnText) loginCloudBtnText.textContent = "☁️ Firebase Cloud Setup";
    if (loginSubtitle) loginSubtitle.textContent = "Enter your Parent Master PIN to access controls";
  }
}

function openCloudModal() {
  cfgFbUrl.value = fbUrl || "https://my-focus-app-c316d-default-rtdb.firebaseio.com";
  cfgFbSecret.value = fbSecret;
  cloudModal.style.display = "flex";
}

loginCloudBtn?.addEventListener("click", openCloudModal);
cloudCfgBtn?.addEventListener("click", openCloudModal);

closeCloudBtn?.addEventListener("click", () => {
  cloudModal.style.display = "none";
});

saveCloudBtn?.addEventListener("click", () => {
  fbUrl = cfgFbUrl.value.trim();
  fbSecret = cfgFbSecret.value.trim();
  localStorage.setItem("focus_fb_url", fbUrl);
  localStorage.setItem("focus_fb_secret", fbSecret);
  cloudModal.style.display = "none";
  updateCloudModeIndicator();
  alert("Firebase Cloud credentials saved! Now enter your Parent Master PIN to unlock.");
  if (authToken) {
    pollStatus();
  }
});

async function sendAction(action, extraPayload = {}) {
  const cmdId = extraPayload.id || ("cmd_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9));
  const payload = { id: cmdId, action, timestamp: Date.now(), ...extraPayload };
  console.log("[FOCUS Dashboard] Dispatching action:", action, payload);
  if (fbUrl) {
    const cleanUrl = fbUrl.replace(/\/$/, "");
    const url = `${cleanUrl}/focus/command.json?auth=${fbSecret}`;
    await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    // Auto-clear transient power actions after 3s so stale commands never persist in Firebase
    if (["lock", "signout", "restart", "shutdown"].includes(action)) {
      setTimeout(() => {
        fetch(`${cleanUrl}/focus/command.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "cleared", id: "cleared_" + cmdId, timestamp: Date.now() }),
        }).catch(() => { });
      }, 3000);
    }

    // Optimistically update cloud status nodes so polling never flips switches back
    try {
      if (action === "focus") {
        await fetch(`${cleanUrl}/focus/status/focus_mode.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Boolean(extraPayload.enabled)),
        });
        await fetch(`${cleanUrl}/focus/rules/focus_mode.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Boolean(extraPayload.enabled)),
        });
        const expiresAt = extraPayload.duration_mins > 0 ? (Date.now() / 1000) + (extraPayload.duration_mins * 60) : 0;
        await fetch(`${cleanUrl}/focus/status/focus_expires_at.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(expiresAt),
        });
        await fetch(`${cleanUrl}/focus/rules/focus_expires_at.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(expiresAt),
        });
        if (extraPayload.enabled && extraPayload.max_tabs !== undefined) {
          await fetch(`${cleanUrl}/focus/status/max_tabs.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.max_tabs),
          });
          await fetch(`${cleanUrl}/focus/rules/max_tabs.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.max_tabs),
          });
          if (currentRules) currentRules.max_tabs = extraPayload.max_tabs;
        }
      } else if (action === "keylock") {
        await fetch(`${cleanUrl}/focus/status/keyboard_locked.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Boolean(extraPayload.enabled)),
        });
        await fetch(`${cleanUrl}/focus/rules/keyboard_locked.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Boolean(extraPayload.enabled)),
        });
      } else if (action === "set_tabs") {
        lastTabChangeTime = Date.now();
        await fetch(`${cleanUrl}/focus/status/max_tabs.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.max_tabs),
        });
        await fetch(`${cleanUrl}/focus/rules/max_tabs.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.max_tabs),
        });
        if (currentRules) currentRules.max_tabs = extraPayload.max_tabs;
      } else if (action === "set_tab_range") {
        lastTabChangeTime = Date.now();
        await fetch(`${cleanUrl}/focus/status/min_tabs.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.min_tabs),
        });
        await fetch(`${cleanUrl}/focus/rules/min_tabs.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.min_tabs),
        });
        await fetch(`${cleanUrl}/focus/status/max_tabs_range.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.max_tabs_range),
        });
        await fetch(`${cleanUrl}/focus/rules/max_tabs_range.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(extraPayload.max_tabs_range),
        });
        if (extraPayload.max_tabs !== undefined) {
          await fetch(`${cleanUrl}/focus/status/max_tabs.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.max_tabs),
          });
          await fetch(`${cleanUrl}/focus/rules/max_tabs.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.max_tabs),
          });
        }
        if (currentRules) {
          currentRules.min_tabs = extraPayload.min_tabs;
          currentRules.max_tabs_range = extraPayload.max_tabs_range;
          if (extraPayload.max_tabs !== undefined) currentRules.max_tabs = extraPayload.max_tabs;
        }
      } else if (action === "set_request_policy") {
        if (extraPayload.policy !== undefined) {
          await fetch(`${cleanUrl}/focus/status/auto_request_policy.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.policy),
          });
          await fetch(`${cleanUrl}/focus/rules/auto_request_policy.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extraPayload.policy),
          });
        }
        if (extraPayload.auto_decline_during_focus !== undefined) {
          await fetch(`${cleanUrl}/focus/status/auto_decline_during_focus.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Boolean(extraPayload.auto_decline_during_focus)),
          });
          await fetch(`${cleanUrl}/focus/rules/auto_decline_during_focus.json?auth=${fbSecret}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Boolean(extraPayload.auto_decline_during_focus)),
          });
        }
      }
    } catch (e) { }
  } else {
    await apiFetch("/api/action", { method: "POST", body: payload });
  }
}

async function apiFetch(endpoint, options = {}) {
  options.headers = options.headers || {};
  if (authToken) {
    options.headers["Authorization"] = `Bearer ${authToken}`;
  }
  if (options.body && typeof options.body === "object") {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, options);
  if (response.status === 401) {
    handleUnauthorized();
    throw new Error("Unauthorized");
  }
  return response;
}

function handleUnauthorized() {
  authToken = "";
  localStorage.removeItem("focus_parent_token");
  loginModal.style.display = "flex";
  appContainer.style.display = "none";
  updateCloudModeIndicator();
}

async function sha256Hex(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str.trim()));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

// --- 2. Authentication ---
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  const pin = pinInput.value.trim();
  if (!pin) return;

  const isCloudHost = window.location.hostname.includes("github.io") || !!fbUrl;

  if (isCloudHost) {
    if (!fbUrl || !fbSecret) {
      loginError.textContent = "Firebase credentials not linked on this phone! Click 'Firebase Cloud Setup' below.";
      openCloudModal();
      return;
    }

    try {
      loginError.style.color = "var(--primary)";
      loginError.textContent = "Connecting to Firebase RTDB...";

      const cleanUrl = fbUrl.replace(/\/$/, "");
      const enteredHash = await sha256Hex(pin);

      let res = await fetch(`${cleanUrl}/focus/security.json?auth=${fbSecret}`);
      let secData = res.ok ? await res.json() : null;
      let validHash = secData?.pin_hash;

      if (!validHash) {
        const rulesRes = await fetch(`${cleanUrl}/focus/rules.json?auth=${fbSecret}`);
        if (rulesRes.ok) {
          const rulesData = await rulesRes.json();
          validHash = rulesData?.pin_hash;
        }
      }

      // If PC daemon hasn't initialized pin_hash yet, initialize it with parent's pin
      if (!validHash) {
        await fetch(`${cleanUrl}/focus/security.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin_hash: enteredHash }),
        });
        validHash = enteredHash;
      }

      if (enteredHash === validHash) {
        authToken = "cloud_" + Date.now();
        localStorage.setItem("focus_parent_token", authToken);
        loginModal.style.display = "none";
        appContainer.style.display = "flex";
        pinInput.value = "";
        loginError.textContent = "";
        loginError.style.color = "var(--danger)";
        initDashboard();
      } else {
        loginError.style.color = "var(--danger)";
        loginError.textContent = "Incorrect Master PIN. Access denied.";
      }
    } catch (err) {
      loginError.style.color = "var(--danger)";
      loginError.textContent = "Firebase connection failed. Check your URL & Secret.";
    }
  } else {
    // Local daemon API login
    try {
      const res = await fetch(`${API_BASE}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const data = await res.json();
      if (data.success && data.token) {
        authToken = data.token;
        localStorage.setItem("focus_parent_token", authToken);
        loginModal.style.display = "none";
        appContainer.style.display = "flex";
        pinInput.value = "";
        initDashboard();
      } else {
        loginError.textContent = data.error || "Incorrect Master PIN";
      }
    } catch (err) {
      loginError.textContent = "Server unreachable. Click 'Firebase Cloud Setup' below to link cloud.";
    }
  }
});

logoutBtn.addEventListener("click", () => {
  handleUnauthorized();
});

// --- 3. Dashboard Initialization & State Polling ---
async function initDashboard() {
  await fetchRules();
  await fetchRequests();
  await pollStatus();
  setInterval(pollStatus, 2500);
}

async function pollStatus() {
  try {
    let data;
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const res = await fetch(`${cleanUrl}/focus/status.json?auth=${fbSecret}`);
      if (!res.ok) return;
      data = await res.json();
    } else {
      if (!authToken) return;
      const res = await apiFetch("/api/status");
      if (!res.ok) return;
      data = await res.json();
    }
    if (!data) return;

    // Connection Status & Liveness Detection
    const nowSecs = Math.floor(Date.now() / 1000);
    const lastSeen = Number(data.last_seen || 0);
    const isOnline = lastSeen > 0 ? (nowSecs - lastSeen < 20) : Boolean(data.online && !fbUrl);

    if (isOnline) {
      statusPill.className = "status-pill online";
      statusText.textContent = fbUrl ? "Cloud" : "Local";

      if (_pcWasOffline) {
        _pcWasOffline = false;
        _lastOnlineTime = Date.now();
      }
    } else {
      statusPill.className = "status-pill offline";
      statusText.textContent = fbUrl ? "PC Offline" : "Disconnected";
      _pcWasOffline = true;
    }

    // Focus Mode (prevent snapback while user recently clicked OR just reconnected)
    const isInteractingFocus = (Date.now() - lastFocusToggleTime) < RECONNECT_FREEZE_MS;
    if (!isInteractingFocus && data.focus_mode !== undefined) {
      toggleFocus.checked = Boolean(data.focus_mode);
      if (data.focus_mode) {
        if (data.focus_expires_at > 0) {
          const remainingSecs = Math.max(0, Math.floor(data.focus_expires_at - (Date.now() / 1000)));
          const mins = Math.floor(remainingSecs / 60);
          focusStatusBadge.textContent = `Active (${mins}m left)`;
        } else {
          focusStatusBadge.textContent = "Active (Unlimited)";
        }
        focusStatusBadge.className = "badge badge-primary";
      } else {
        focusStatusBadge.textContent = "Standby (All Limits OFF)";
        focusStatusBadge.className = "badge";
      }
    }

    // Keyboard Lock (prevent snapback while user recently clicked OR just reconnected)
    const isInteractingKeylock = (Date.now() - lastKeylockToggleTime) < RECONNECT_FREEZE_MS;
    if (!isInteractingKeylock && data.keyboard_locked !== undefined) {
      toggleKeylock.checked = Boolean(data.keyboard_locked);
    }

    // Active App & Window
    if (data.active_window) {
      const appName = data.active_window.app || "Desktop";
      const winTitle = data.active_window.title || "Idle";
      activeAppName.textContent = appName;
      activeAppName.title = appName;

      // Hard-cap title length to max 40 chars with '...' to completely prevent any layout shift
      const MAX_TITLE_LEN = 40;
      const displayTitle = winTitle.length > MAX_TITLE_LEN
        ? winTitle.substring(0, MAX_TITLE_LEN - 3).trim() + "..."
        : winTitle;

      activeWindowTitle.textContent = displayTitle;
      activeWindowTitle.title = winTitle; // Full title available on hover
    }

    // Tab Limits & Range Bounds (prevent snapback while user recently adjusted tabs OR just reconnected)
    const isInteractingTabs = (Date.now() - lastTabChangeTime) < RECONNECT_FREEZE_MS;
    if (!isInteractingTabs) {
      if (data.min_tabs !== undefined && data.max_tabs_range !== undefined) {
        const minVal = parseInt(data.min_tabs, 10);
        const maxRangeVal = parseInt(data.max_tabs_range, 10);
        if (cfgMinTabs && cfgMaxTabsRange && !cfgMinTabs.matches(":focus") && !cfgMaxTabsRange.matches(":focus")) {
          if (parseInt(cfgMinTabs.value, 10) !== minVal || parseInt(cfgMaxTabsRange.value, 10) !== maxRangeVal) {
            updateTabRange(minVal, maxRangeVal, false);
          }
        }
      }

      if (data.max_tabs !== undefined && !tabSlider.matches(":active")) {
        const val = parseInt(data.max_tabs, 10);
        tabSlider.value = val;
        tabSliderVal.textContent = val === 1 ? "1 Tab" : `${val} Tabs`;
        tabCountBadge.textContent = `${val} ${val === 1 ? 'Tab' : 'Tabs'} Max`;
      }
    }

    // Request Automation Policy
    if (data.auto_request_policy !== undefined) {
      updatePolicyUI(data.auto_request_policy, Boolean(data.auto_decline_during_focus));
    }

    // Update Access Requests
    await fetchRequests();
  } catch (err) {
    statusPill.className = "status-pill";
    statusText.textContent = "Offline";
  }
}

// --- 4. System Power & Session Actions ---
document.querySelectorAll(".btn-action").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.getAttribute("data-action");
    if (!action) return;

    if (action === "shutdown") {
      if (!confirm("Are you sure you want to SHUT DOWN your brother's computer?")) return;
    } else if (action === "restart") {
      if (!confirm("Are you sure you want to RESTART your brother's computer?")) return;
    }

    try {
      btn.style.opacity = "0.5";
      await sendAction(action);
      setTimeout(() => (btn.style.opacity = "1"), 600);
    } catch (err) {
      alert("Action failed: " + err.message);
      btn.style.opacity = "1";
    }
  });
});

// --- 5. Focus Mode & Keyboard Lock Controls ---
toggleFocus.addEventListener("change", async () => {
  lastFocusToggleTime = Date.now();
  const enabled = toggleFocus.checked;

  if (enabled) {
    focusStatusBadge.textContent = selectedDurationMins > 0 ? `Active (${selectedDurationMins}m)` : "Active (Unlimited)";
    focusStatusBadge.className = "badge badge-primary";

    const minTabs = parseInt(cfgMinTabs?.value || "1", 10);
    const maxRange = parseInt(cfgMaxTabsRange?.value || "15", 10);
    let currentVal = parseInt(tabSlider?.value || minTabs, 10);
    if (currentVal < minTabs) currentVal = minTabs;
    if (currentVal > maxRange) currentVal = maxRange;

    tabSlider.value = currentVal;
    tabSliderVal.textContent = currentVal === 1 ? "1 Tab" : `${currentVal} Tabs`;
    tabCountBadge.textContent = `${currentVal} ${currentVal === 1 ? 'Tab' : 'Tabs'} Max`;

    // Send single atomic command containing max_tabs
    await sendAction("focus", { enabled, duration_mins: selectedDurationMins, max_tabs: currentVal });
  } else {
    focusStatusBadge.textContent = "Standby (All Limits OFF)";
    focusStatusBadge.className = "badge";
    await sendAction("focus", { enabled, duration_mins: selectedDurationMins });
  }
});

// Duration Chips
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    selectedDurationMins = parseInt(chip.getAttribute("data-mins") || "0", 10);

    if (toggleFocus.checked) {
      lastFocusToggleTime = Date.now();
      focusStatusBadge.textContent = selectedDurationMins > 0 ? `Active (${selectedDurationMins}m)` : "Active (Unlimited)";
      sendAction("focus", { enabled: true, duration_mins: selectedDurationMins });
    }
  });
});

toggleKeylock.addEventListener("change", async () => {
  lastKeylockToggleTime = Date.now();
  const enabled = toggleKeylock.checked;
  await sendAction("keylock", { enabled });
});

// --- 6. Tab Limiter Slider & Configurable Range Bounds ---
function updateTabRange(minVal, maxRangeVal, shouldDispatch = true) {
  lastTabChangeTime = Date.now();
  const oldMin = parseInt(cfgMinTabs?.value || "1", 10);
  minVal = Math.max(1, parseInt(minVal || "1", 10));
  maxRangeVal = Math.max(minVal, parseInt(maxRangeVal || "15", 10));

  if (cfgMinTabs) cfgMinTabs.value = minVal;
  if (cfgMaxTabsRange) cfgMaxTabsRange.value = maxRangeVal;

  if (tabSlider) {
    let currVal = parseInt(tabSlider.value || minVal, 10);
    // If slider was pinned to previous min, keep it aligned with new min
    if (currVal === oldMin || currVal < minVal) {
      currVal = minVal;
    } else if (currVal > maxRangeVal) {
      currVal = maxRangeVal;
    }

    tabSlider.min = minVal;
    tabSlider.max = maxRangeVal;
    tabSlider.value = currVal;

    if (tabSliderVal) tabSliderVal.textContent = currVal === 1 ? "1 Tab" : `${currVal} Tabs`;
    if (tabCountBadge) tabCountBadge.textContent = `${currVal} ${currVal === 1 ? 'Tab' : 'Tabs'} Max`;
  }

  if (tabSliderMinLabel) tabSliderMinLabel.textContent = `${minVal} ${minVal === 1 ? 'Tab' : 'Tabs'} (Min)`;
  if (tabSliderMaxLabel) tabSliderMaxLabel.textContent = `${maxRangeVal} Tabs (Max)`;

  if (shouldDispatch) {
    const currVal = parseInt(tabSlider ? tabSlider.value : minVal, 10);
    sendAction("set_tab_range", { min_tabs: minVal, max_tabs_range: maxRangeVal, max_tabs: currVal });
  }
}

btnDecMinTabs?.addEventListener("click", () => {
  const currentMin = parseInt(cfgMinTabs.value || "1", 10);
  if (currentMin > 1) {
    updateTabRange(currentMin - 1, parseInt(cfgMaxTabsRange.value || "15", 10));
  }
});

btnIncMinTabs?.addEventListener("click", () => {
  const currentMin = parseInt(cfgMinTabs.value || "1", 10);
  const currentMax = parseInt(cfgMaxTabsRange.value || "15", 10);
  if (currentMin < currentMax) {
    updateTabRange(currentMin + 1, currentMax);
  }
});

btnDecMaxTabs?.addEventListener("click", () => {
  const currentMin = parseInt(cfgMinTabs.value || "1", 10);
  const currentMax = parseInt(cfgMaxTabsRange.value || "15", 10);
  if (currentMax > currentMin) {
    updateTabRange(currentMin, currentMax - 1);
  }
});

btnIncMaxTabs?.addEventListener("click", () => {
  const currentMin = parseInt(cfgMinTabs.value || "1", 10);
  const currentMax = parseInt(cfgMaxTabsRange.value || "15", 10);
  if (currentMax < 50) {
    updateTabRange(currentMin, currentMax + 1);
  }
});

cfgMinTabs?.addEventListener("change", () => {
  updateTabRange(cfgMinTabs.value, cfgMaxTabsRange.value);
});

cfgMaxTabsRange?.addEventListener("change", () => {
  updateTabRange(cfgMinTabs.value, cfgMaxTabsRange.value);
});

let tabDebounceTimer;
tabSlider.addEventListener("input", (e) => {
  lastTabChangeTime = Date.now();
  const val = parseInt(e.target.value, 10);
  tabSliderVal.textContent = val === 1 ? "1 Tab" : `${val} Tabs`;
  tabCountBadge.textContent = `${val} ${val === 1 ? 'Tab' : 'Tabs'} Max`;

  clearTimeout(tabDebounceTimer);
  tabDebounceTimer = setTimeout(async () => {
    lastTabChangeTime = Date.now();
    await sendAction("set_tabs", { max_tabs: val });
  }, 400);
});

// --- 7. Live Screenshot ---
refreshScreenBtn.addEventListener("click", async () => {
  refreshScreenBtn.disabled = true;
  refreshScreenBtn.textContent = "Capturing...";
  try {
    if (fbUrl) {
      const cmdId = "cmd_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
      const requestTimestamp = (Date.now() / 1000) - 15;
      await sendAction("screenshot", { id: cmdId });
      const cleanUrl = fbUrl.replace(/\/$/, "");

      let captured = false;
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const res = await fetch(`${cleanUrl}/focus/screenshot.json?auth=${fbSecret}`);
          if (res.ok) {
            const data = await res.json();
            if (data && data.image) {
              const matchCmd = data.cmd_id && data.cmd_id === cmdId;
              const matchTime = Number(data.timestamp || 0) >= requestTimestamp;
              if (matchCmd || matchTime) {
                screenshotImg.src = data.image;
                screenshotContainer.style.display = "block";
                captured = true;
                break;
              }
            }
          }
        } catch (pollErr) { }
      }
      if (!captured) {
        alert("Screenshot request timed out. Ensure the PC app is running and connected.");
      }
    } else {
      const res = await apiFetch("/api/screenshot");
      if (res.ok) {
        const blob = await res.blob();
        const imgUrl = URL.createObjectURL(blob);
        screenshotImg.src = imgUrl;
        screenshotContainer.style.display = "block";
      }
    }
  } catch (err) {
    alert("Failed to capture screenshot: " + err.message);
  } finally {
    refreshScreenBtn.disabled = false;
    refreshScreenBtn.textContent = "📷 Take Live Screenshot";
  }
});

// --- 7.5 Access Requests & Notifications ---
let _currentRequests = [];
let _showRequestsHistory = false;

async function fetchRequests() {
  try {
    let requests = [];
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const res = await fetch(`${cleanUrl}/focus/requests.json?auth=${fbSecret}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          requests = data;
        } else if (data && typeof data === "object") {
          requests = Object.values(data);
        }
      }
    } else {
      if (!authToken) return;
      const res = await apiFetch("/api/requests");
      if (res.ok) {
        const data = await res.json();
        requests = data.requests || [];
      }
    }
    _currentRequests = requests;
    renderAccessRequests(requests);
  } catch (err) {
    console.error("[FOCUS Dashboard] Error fetching requests:", err);
  }
}

function renderAccessRequests(requests) {
  if (!requestsListContainer) return;

  const allReqs = requests || [];
  const pendingReqs = allReqs.filter((r) => r.status === "pending");
  const historyReqs = allReqs.filter((r) => r.status !== "pending");

  const pendingCount = pendingReqs.length;
  if (pendingRequestsBadge) {
    pendingRequestsBadge.textContent = `${pendingCount} Pending`;
    if (!_showRequestsHistory) {
      pendingRequestsBadge.className = pendingCount > 0 ? "btn-header-pill active-primary" : "btn-header-pill active";
      pendingRequestsBadge.title = "Viewing pending access requests";
    } else {
      pendingRequestsBadge.className = "btn-header-pill";
      pendingRequestsBadge.title = "Switch to pending access requests";
    }
  }

  const btnToggle = document.getElementById("btn-toggle-history");
  const sectionTitle = document.getElementById("requests-section-title");
  const sectionDesc = document.getElementById("requests-section-desc");

  if (btnToggle) {
    if (_showRequestsHistory) {
      btnToggle.className = "btn-header-pill active-history";
      btnToggle.title = "Viewing past approved and rejected access requests";
      if (sectionTitle) sectionTitle.textContent = "Request History";
      if (sectionDesc) sectionDesc.textContent = "Past approved and rejected access requests from workstation.";
    } else {
      btnToggle.className = "btn-header-pill";
      btnToggle.title = "Switch to request history";
      if (sectionTitle) sectionTitle.textContent = "Access Requests";
      if (sectionDesc) sectionDesc.textContent = "Study access requests submitted from workstation. Tap Allow to whitelist instantly, Reject to dismiss, or View to inspect URL.";
    }
  }

  const listToRender = _showRequestsHistory ? historyReqs : pendingReqs;

  if (listToRender.length === 0) {
    if (_showRequestsHistory) {
      requestsListContainer.innerHTML = `
        <div class="no-requests-msg" id="no-requests-placeholder">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.4; margin-bottom:4px;">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
          <span>No request history yet. Approved and rejected requests will appear here.</span>
        </div>
      `;
    } else {
      requestsListContainer.innerHTML = `
        <div class="no-requests-msg" id="no-requests-placeholder">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.4; margin-bottom:4px;">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 6v6l4 2"></path>
          </svg>
          <span>No pending access requests. System is operating normally.</span>
        </div>
      `;
    }
    return;
  }

  requestsListContainer.innerHTML = "";

  // Sort by newest first
  listToRender.sort((a, b) => {
    const timeA = Number(a.resolved_at || a.timestamp || 0);
    const timeB = Number(b.resolved_at || b.timestamp || 0);
    return timeB - timeA;
  });

  listToRender.forEach((req) => {
    const card = document.createElement("div");
    card.className = `request-card status-${req.status || "pending"}`;

    const reqType = (req.type || "website").toLowerCase();
    let typeIconHtml = "";
    let typeLabel = "Website";

    if (reqType === "channel") {
      typeLabel = "YouTube Channel";
      typeIconHtml = `
        <div class="request-type-icon icon-channel" title="YouTube Channel">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="7" width="20" height="15" rx="2" ry="2"></rect>
            <polyline points="17 2 12 7 7 2"></polyline>
          </svg>
        </div>
      `;
    } else if (reqType === "video") {
      typeLabel = "YouTube Video";
      typeIconHtml = `
        <div class="request-type-icon icon-video" title="YouTube Video">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polygon points="10 8 16 12 10 16 10 8"></polygon>
          </svg>
        </div>
      `;
    } else {
      typeLabel = "Website";
      typeIconHtml = `
        <div class="request-type-icon icon-website" title="Website Domain">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
          </svg>
        </div>
      `;
    }

    const title = req.title || req.target || "Requested Item";
    const target = req.target || req.url || "";
    const url = req.url || (req.target && req.target.startsWith("http") ? req.target : `https://${req.target}`);

    // Time formatting
    let timeStr = "Recently";
    if (req.timestamp) {
      const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - req.timestamp));
      if (elapsed < 60) timeStr = "Just now";
      else if (elapsed < 3600) timeStr = `${Math.floor(elapsed / 60)}m ago`;
      else if (elapsed < 86400) timeStr = `${Math.floor(elapsed / 3600)}h ago`;
      else timeStr = `${Math.floor(elapsed / 86400)}d ago`;
    }

    let actionsHtml = "";
    if (req.status === "pending") {
      actionsHtml = `
        <div class="request-actions">
          <button class="btn-request btn-request-allow" data-id="${req.id}" title="Approve and auto-add to whitelist">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Allow
          </button>
          <button class="btn-request btn-request-reject" data-id="${req.id}" title="Reject request and keep restricted">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
            Reject
          </button>
          <button class="btn-request btn-request-view" data-url="${encodeURIComponent(url)}" title="Open and inspect content in new tab">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
            View
          </button>
        </div>
      `;
    } else if (req.status === "approved") {
      const isAuto = req.resolved_by === "auto_approve";
      actionsHtml = `
        <div class="request-actions">
          <span class="request-status-pill request-status-approved ${isAuto ? 'badge-auto-approved' : ''}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            ${isAuto ? 'Auto-Approved' : 'Allowed'}
          </span>
          <div class="request-action-btns">
            <button class="btn-request btn-request-view" data-url="${encodeURIComponent(url)}" title="Open link in new tab">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              View
            </button>
            <button class="btn-request btn-request-delete" data-id="${req.id || ''}" title="Delete this request from history">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
      `;
    } else {
      const isAuto = req.resolved_by === "auto_decline";
      actionsHtml = `
        <div class="request-actions">
          <span class="request-status-pill request-status-rejected ${isAuto ? 'badge-auto-declined' : ''}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
            ${isAuto ? 'Auto-Declined' : 'Rejected'}
          </span>
          <div class="request-action-btns">
            <button class="btn-request btn-request-view" data-url="${encodeURIComponent(url)}" title="Open link in new tab">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              View
            </button>
            <button class="btn-request btn-request-delete" data-id="${req.id || ''}" title="Delete this request from history">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="request-card-info">
        ${typeIconHtml}
        <div class="request-card-text">
          <div class="request-title" title="${title}">${title}</div>
          <div class="request-subtitle">
            <span class="request-meta-tag">${typeLabel}</span>
            <span>&bull;</span>
            <span>${timeStr}</span>
            ${req.channel && reqType === "video" ? `<span>&bull;</span><span style="color:var(--text-secondary);">${req.channel}</span>` : ""}
          </div>
        </div>
      </div>
      ${actionsHtml}
    `;

    // Bind Allow button
    card.querySelector(".btn-request-allow")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await handleResolveRequest(req.id, "allow", req);
    });

    // Bind Reject button
    card.querySelector(".btn-request-reject")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await handleResolveRequest(req.id, "reject", req);
    });

    // Bind View button
    card.querySelector(".btn-request-view")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const targetUrl = decodeURIComponent(e.currentTarget.getAttribute("data-url") || url);
      window.open(targetUrl, "_blank", "noopener,noreferrer");
    });

    // Bind Delete button
    card.querySelector(".btn-request-delete")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      const idToDelete = req.id || e.currentTarget.getAttribute("data-id");
      await handleDeleteRequest(idToDelete, req);
    });

    requestsListContainer.appendChild(card);

  });
}

document.getElementById("btn-toggle-history")?.addEventListener("click", () => {
  _showRequestsHistory = true;
  renderAccessRequests(_currentRequests);
});

pendingRequestsBadge?.addEventListener("click", () => {
  _showRequestsHistory = false;
  renderAccessRequests(_currentRequests);
});

// --- Request Automation Policy State & Handlers ---
let _currentPolicy = "manual";
let _lastPolicyChangeTime = 0;

function updatePolicyUI(policy, declineDuringFocus) {
  // Prevent snapback if user recently clicked policy buttons
  if (Date.now() - _lastPolicyChangeTime < 3000) return;
  _currentPolicy = policy || "manual";

  document.querySelectorAll(".policy-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-policy") === _currentPolicy);
  });

  const activeLabel = document.getElementById("policy-active-label");
  if (activeLabel) {
    activeLabel.className = `policy-status-indicator mode-${_currentPolicy}`;
    if (_currentPolicy === "approve") {
      activeLabel.textContent = "⚡ Auto-Approve Active";
    } else if (_currentPolicy === "decline") {
      activeLabel.textContent = "⛔ Auto-Decline Active";
    } else {
      activeLabel.textContent = "Manual Review";
    }
  }

  const checkFocus = document.getElementById("check-auto-decline-focus");
  if (checkFocus && declineDuringFocus !== undefined && !checkFocus.matches(":focus")) {
    checkFocus.checked = Boolean(declineDuringFocus);
  }
}

document.querySelectorAll(".policy-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const policy = btn.getAttribute("data-policy");
    if (!policy) return;
    _lastPolicyChangeTime = Date.now();
    updatePolicyUI(policy);
    await sendAction("set_request_policy", { policy });
  });
});

const checkAutoDeclineFocus = document.getElementById("check-auto-decline-focus");
if (checkAutoDeclineFocus) {
  checkAutoDeclineFocus.addEventListener("change", async () => {
    _lastPolicyChangeTime = Date.now();
    await sendAction("set_request_policy", { auto_decline_during_focus: checkAutoDeclineFocus.checked });
  });
}

async function handleResolveRequest(reqId, decision, req) {
  try {
    // 1. Dispatch action to PC coordinator
    await sendAction("resolve_request", {
      id: "cmd_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9),
      request_id: reqId,
      decision: decision
    });

    // 2. Optimistic local & cloud update
    const targetStatus = decision === "allow" ? "approved" : "rejected";
    if (req) {
      req.status = targetStatus;
    }
    const found = _currentRequests.find((r) => r.id === reqId);
    if (found) {
      found.status = targetStatus;
    }

    // Auto-update rules tag clouds optimistically if allowed
    if (decision === "allow" && req) {
      const reqType = (req.type || "").toLowerCase();
      if (reqType === "channel" && req.target) {
        const clean = "@" + req.target.replace(/^@/, "");
        if (!currentRules.allowed_channels.includes(clean)) {
          currentRules.allowed_channels.push(clean);
        }
      } else if (reqType === "website" && req.target) {
        const clean = req.target.toLowerCase().replace(/^https?:\/\//, "").split("/")[0];
        if (!currentRules.allowed_sites.includes(clean)) {
          currentRules.allowed_sites.push(clean);
        }
      } else if (reqType === "video") {
        // Option 2: Whitelist only this specific video; keep the rest of the channel restricted
        const vId = extractVideoIdClient(req.target || req.url || "");
        if (vId) {
          currentRules.allowed_videos = currentRules.allowed_videos || [];
          const exists = currentRules.allowed_videos.some((item) => {
            const existingId = (typeof item === "object") ? item.id : item;
            return existingId === vId;
          });
          if (!exists) {
            currentRules.allowed_videos.push({
              id: vId,
              title: req.title || `Video (${vId})`,
              channel: req.channel || ""
            });
          }
        }
      }
      renderTagClouds();
    }

    // Push directly to Firebase if connected so phone/cloud UI stays 100% in sync
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      fetch(`${cleanUrl}/focus/requests.json?auth=${fbSecret}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_currentRequests)
      }).catch(() => { });
      if (decision === "allow") {
        fetch(`${cleanUrl}/focus/rules.json?auth=${fbSecret}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(currentRules)
        }).catch(() => { });
      }
    }

    // Re-render UI immediately
    renderAccessRequests(_currentRequests);
  } catch (err) {
    alert("Failed to resolve request: " + err.message);
  }
}

async function handleDeleteRequest(reqId, reqObj) {
  if (!reqId && !reqObj) return;
  const targetId = String(reqId || reqObj?.id || "").trim();
  const targetVal = String(reqObj?.target || reqObj?.url || "").trim();

  try {
    // 1. Optimistic local update (filter by ID or target)
    _currentRequests = _currentRequests.filter((r) => {
      const rId = String(r.id || "").trim();
      const rTarget = String(r.target || r.url || "").trim();
      if (targetId && rId === targetId) return false;
      if (targetVal && rTarget === targetVal) return false;
      return true;
    });
    renderAccessRequests(_currentRequests);

    // 2. Direct PUT to Firebase RTDB (awaiting response so it persists before any refresh)
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const authQuery = fbSecret ? `?auth=${encodeURIComponent(fbSecret)}` : "";
      try {
        const res = await fetch(`${cleanUrl}/focus/requests.json${authQuery}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(_currentRequests)
        });
        if (res.ok) {
          console.log("[FOCUS Dashboard] Deleted request from Firebase successfully.");
        } else {
          console.warn("[FOCUS Dashboard] Firebase PUT status:", res.status);
        }
      } catch (e) {
        console.warn("[FOCUS Dashboard] Firebase PUT error:", e);
      }
    }

    // 3. Dispatch delete_request action to coordinator (handles both local REST and cloud command)
    if (!fbUrl && authToken) {
      await apiFetch("/api/delete_request", {
        method: "POST",
        body: { request_id: targetId, target: targetVal }
      });
    } else {
      await sendAction("delete_request", {
        request_id: targetId,
        target: targetVal
      });
    }
  } catch (err) {
    console.error("[FOCUS Dashboard] Failed to delete request:", err);
  }
}


// --- 8. Whitelist Management ---
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const tabName = btn.getAttribute("data-tab");
    document.getElementById(`panel-${tabName}`).classList.add("active");
  });
});

async function fetchRules() {
  try {
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const res = await fetch(`${cleanUrl}/focus/rules.json?auth=${fbSecret}`);
      if (res.ok) {
        const data = await res.json();
        if (data && typeof data === "object") {
          currentRules = data;
          renderTagClouds();
        }
      }
    } else {
      const res = await apiFetch("/api/rules");
      if (res.ok) {
        currentRules = await res.json();
        renderTagClouds();
      }
    }
  } catch (err) { }
}

function renderTagClouds() {
  renderCloud("sites", currentRules.allowed_sites || []);
  renderCloud("channels", currentRules.allowed_channels || []);
  renderVideosCloud(currentRules.allowed_videos || []);
}

function renderCloud(type, items) {
  const container = document.getElementById(`tag-cloud-${type}`);
  if (!container) return;
  container.innerHTML = "";
  items.forEach((item) => {
    const tag = document.createElement("div");
    tag.className = "tag";
    tag.innerHTML = `
      <span>${item}</span>
      <span class="tag-remove" data-item="${item}" data-type="${type}">&times;</span>
    `;
    tag.querySelector(".tag-remove").addEventListener("click", () => {
      removeItem(type, item);
    });
    container.appendChild(tag);
  });
}

function extractVideoIdClient(str) {
  if (!str) return "";
  const clean = str.trim();
  const m = clean.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/);
  if (m) return m[1];
  if (/^[a-zA-Z0-9_-]{11}$/.test(clean)) return clean;
  return "";
}

function renderVideosCloud(items) {
  const container = document.getElementById("tag-cloud-videos");
  if (!container) return;
  container.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    container.innerHTML = `<span style="font-size: 11.5px; color: var(--text-dim); padding: 4px 6px;">No individual videos whitelisted.</span>`;
    return;
  }
  items.forEach((item) => {
    const vId = (typeof item === "object") ? item.id : item;
    const title = (typeof item === "object" && item.title) ? item.title : `Video (${vId})`;
    const ch = (typeof item === "object" && item.channel) ? ` • ${item.channel}` : "";
    const displayLabel = title.length > 36 ? title.substring(0, 33) + "..." : title;

    const tag = document.createElement("div");
    tag.className = "tag";
    tag.title = `${title}${ch} (ID: ${vId})`;
    tag.innerHTML = `
      <span>▶ ${displayLabel}</span>
      <span class="tag-remove" data-id="${vId}">&times;</span>
    `;
    tag.querySelector(".tag-remove").addEventListener("click", () => {
      removeVideo(vId);
    });
    container.appendChild(tag);
  });
}

async function addVideo(value) {
  const vId = extractVideoIdClient(value);
  if (!vId) {
    alert("Please enter a valid YouTube video URL or 11-character video ID.");
    return;
  }
  currentRules.allowed_videos = currentRules.allowed_videos || [];
  const exists = currentRules.allowed_videos.some((item) => {
    const existingId = (typeof item === "object") ? item.id : item;
    return existingId === vId;
  });
  if (exists) return;

  currentRules.allowed_videos.push({ id: vId, title: `Video (${vId})` });
  renderTagClouds();
  await syncRulesToServer();
}

async function removeVideo(videoId) {
  currentRules.allowed_videos = (currentRules.allowed_videos || []).filter((item) => {
    const existingId = (typeof item === "object") ? item.id : item;
    return existingId !== videoId;
  });
  renderTagClouds();
  await syncRulesToServer();
}

async function addItem(type, value) {
  const key = `allowed_${type}`;
  currentRules[key] = currentRules[key] || [];
  const cleanVal = value.trim().toLowerCase();
  if (!cleanVal || currentRules[key].includes(cleanVal)) return;

  currentRules[key].push(cleanVal);
  renderTagClouds();
  await syncRulesToServer();
}

async function removeItem(type, value) {
  const key = `allowed_${type}`;
  currentRules[key] = (currentRules[key] || []).filter((i) => i.toLowerCase() !== value.toLowerCase());
  renderTagClouds();
  await syncRulesToServer();
}

async function syncRulesToServer() {
  if (fbUrl) {
    const cleanUrl = fbUrl.replace(/\/$/, "");
    await fetch(`${cleanUrl}/focus/rules.json?auth=${fbSecret}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentRules),
    });
    await sendAction("sync_rules", { rules: currentRules });
  } else {
    await apiFetch("/api/rules", {
      method: "POST",
      body: currentRules,
    });
  }
}

document.getElementById("btn-add-site")?.addEventListener("click", () => {
  const inp = document.getElementById("input-site");
  if (inp) {
    addItem("sites", inp.value);
    inp.value = "";
  }
});
document.getElementById("btn-add-channel")?.addEventListener("click", () => {
  const inp = document.getElementById("input-channel");
  if (inp) {
    addItem("channels", inp.value);
    inp.value = "";
  }
});
document.getElementById("btn-add-video")?.addEventListener("click", () => {
  const inp = document.getElementById("input-video");
  if (inp) {
    addVideo(inp.value);
    inp.value = "";
  }
});

// --- 10. Remote App Maintenance & GitHub Sync ---
const btnRemoteUpdate = document.getElementById("btn-remote-update");
const btnRemoteUpdateText = document.getElementById("btn-remote-update-text");
const updateStatusBadge = document.getElementById("update-status-badge");
const updateOutputBox = document.getElementById("update-output-box");

btnRemoteUpdate?.addEventListener("click", async () => {
  if (!confirm("Update FOCUS on your brother's PC from GitHub? The PC app will download new code and reload automatically.")) return;

  btnRemoteUpdate.disabled = true;
  btnRemoteUpdateText.textContent = "Updating PC from GitHub...";
  updateStatusBadge.style.display = "inline-block";
  updateStatusBadge.className = "badge";
  updateStatusBadge.textContent = "In Progress...";
  updateOutputBox.style.display = "none";
  updateOutputBox.textContent = "";

  const cmdId = "cmd_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);

  try {
    await sendAction("update_app", { id: cmdId });

    // Poll for update result (up to 30 seconds)
    let attempts = 0;
    const maxAttempts = 15;
    const checkUpdate = async () => {
      attempts++;
      let status = null;

      if (fbUrl) {
        const cleanUrl = fbUrl.replace(/\/$/, "");
        const res = await fetch(`${cleanUrl}/focus/update_status.json?auth=${fbSecret}`);
        if (res.ok) {
          status = await res.json();
        }
      }

      // Check if status belongs to current command or was produced within last 30s
      const isCurrent = status && (status.cmd_id === cmdId || (status.timestamp && (Date.now() / 1000 - status.timestamp < 30)));

      if (status && isCurrent) {
        if (status.success) {
          if (status.has_updates) {
            updateStatusBadge.className = "badge badge-primary";
            updateStatusBadge.textContent = "✅ Updated & Reloaded";
          } else {
            updateStatusBadge.className = "badge";
            updateStatusBadge.textContent = "ℹ️ Already Up to Date";
          }
        } else {
          updateStatusBadge.className = "badge badge-danger";
          updateStatusBadge.textContent = "❌ Update Failed";
        }

        if (status.output) {
          updateOutputBox.style.display = "block";
          updateOutputBox.textContent = status.output;
        }

        btnRemoteUpdate.disabled = false;
        btnRemoteUpdateText.textContent = "Sync & Update App from GitHub";
        return;
      }

      if (attempts < maxAttempts) {
        setTimeout(checkUpdate, 2000);
      } else {
        btnRemoteUpdate.disabled = false;
        btnRemoteUpdateText.textContent = "Sync & Update App from GitHub";
        updateStatusBadge.className = "badge";
        updateStatusBadge.textContent = "ℹ️ Request Sent";
      }
    };

    setTimeout(checkUpdate, 2000);
  } catch (err) {
    alert("Failed to send update request: " + err.message);
    btnRemoteUpdate.disabled = false;
    btnRemoteUpdateText.textContent = "Sync & Update App from GitHub";
    updateStatusBadge.style.display = "none";
  }
});

// --- 11. Mobile Bottom Navigation Active Tracking ---
document.querySelectorAll(".bottom-nav .nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".bottom-nav .nav-item").forEach((i) => i.classList.remove("active"));
    item.classList.add("active");
  });
});

// Intersection observer to automatically update active bottom nav item during scroll
const navObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      const id = entry.target.id;
      const navItem = document.querySelector(`.bottom-nav a[href="#${id}"]`);
      if (navItem) {
        document.querySelectorAll(".bottom-nav .nav-item").forEach((i) => i.classList.remove("active"));
        navItem.classList.add("active");
      }
    }
  });
}, { threshold: 0.35 });

document.querySelectorAll("section.card[id]").forEach((sec) => navObserver.observe(sec));

// Auto login if token exists
if (authToken) {
  loginModal.style.display = "none";
  appContainer.style.display = "block";
  initDashboard();
} else {
  loginModal.style.display = "flex";
  appContainer.style.display = "none";
}

// Initialize Cloud mode indicators
updateCloudModeIndicator();
