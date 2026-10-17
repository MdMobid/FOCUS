/**
 * FOCUS Parent Dashboard Client
 * Real-time REST & Firebase Cloud sync, authentication, and system control.
 */

const API_BASE = window.location.origin;
let authToken = localStorage.getItem("focus_parent_token") || "";
let fbUrl = localStorage.getItem("focus_fb_url") || "";
let fbSecret = localStorage.getItem("focus_fb_secret") || "";
let selectedDurationMins = 0;
let currentRules = { allowed_apps: [], allowed_sites: [], allowed_channels: [] };

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

const activeAppName = document.getElementById("active-app-name");
const activeWindowTitle = document.getElementById("active-window-title");
const refreshScreenBtn = document.getElementById("refresh-screen-btn");
const screenshotContainer = document.getElementById("screenshot-container");
const screenshotImg = document.getElementById("screenshot-img");

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
  const payload = { action, timestamp: Date.now(), ...extraPayload };
  if (fbUrl) {
    const cleanUrl = fbUrl.replace(/\/$/, "");
    const url = `${cleanUrl}/focus/command.json?auth=${fbSecret}`;
    await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
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

    // Connection Status
    statusPill.className = "status-pill online";
    statusText.textContent = fbUrl ? "Cloud (Live)" : "Local";

    // Focus Mode
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
      focusStatusBadge.textContent = "Standby";
      focusStatusBadge.className = "badge";
    }

    // Keyboard Lock
    toggleKeylock.checked = Boolean(data.keyboard_locked);

    // Active App & Window
    if (data.active_window) {
      activeAppName.textContent = data.active_window.app || "Desktop";
      activeWindowTitle.textContent = data.active_window.title || "Idle";
    }

    // Tab Limit
    if (data.max_tabs !== undefined && !tabSlider.matches(":active")) {
      tabSlider.value = data.max_tabs;
      tabSliderVal.textContent = `${data.max_tabs} Tabs`;
      tabCountBadge.textContent = `${data.max_tabs} Tabs Max`;
    }
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
  const enabled = toggleFocus.checked;
  await sendAction("focus", { enabled, duration_mins: selectedDurationMins });
  pollStatus();
});

// Duration Chips
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    selectedDurationMins = parseInt(chip.getAttribute("data-mins") || "0", 10);

    if (toggleFocus.checked) {
      sendAction("focus", { enabled: true, duration_mins: selectedDurationMins });
    }
  });
});

toggleKeylock.addEventListener("change", async () => {
  const enabled = toggleKeylock.checked;
  await sendAction("keylock", { enabled });
  pollStatus();
});

// --- 6. Tab Limiter Slider ---
let tabDebounceTimer;
tabSlider.addEventListener("input", (e) => {
  const val = e.target.value;
  tabSliderVal.textContent = `${val} Tabs`;
  tabCountBadge.textContent = `${val} Tabs Max`;

  clearTimeout(tabDebounceTimer);
  tabDebounceTimer = setTimeout(async () => {
    await sendAction("set_tabs", { max_tabs: parseInt(val, 10) });
  }, 400);
});

// --- 7. Live Screenshot ---
refreshScreenBtn.addEventListener("click", async () => {
  refreshScreenBtn.disabled = true;
  refreshScreenBtn.textContent = "Capturing...";
  try {
    if (fbUrl) {
      await sendAction("screenshot");
      await new Promise((r) => setTimeout(r, 2000));
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const res = await fetch(`${cleanUrl}/focus/screenshot.json?auth=${fbSecret}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.image) {
          screenshotImg.src = data.image;
          screenshotContainer.style.display = "block";
        } else {
          alert("Screenshot was not yet received. Try clicking again in a few seconds.");
        }
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
  renderCloud("apps", currentRules.allowed_apps || []);
  renderCloud("sites", currentRules.allowed_sites || []);
  renderCloud("channels", currentRules.allowed_channels || []);
}

function renderCloud(type, items) {
  const container = document.getElementById(`tag-cloud-${type}`);
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

document.getElementById("btn-add-app").addEventListener("click", () => {
  const inp = document.getElementById("input-app");
  addItem("apps", inp.value);
  inp.value = "";
});
document.getElementById("btn-add-site").addEventListener("click", () => {
  const inp = document.getElementById("input-site");
  addItem("sites", inp.value);
  inp.value = "";
});
document.getElementById("btn-add-channel").addEventListener("click", () => {
  const inp = document.getElementById("input-channel");
  addItem("channels", inp.value);
  inp.value = "";
});

// --- 9. Installed Applications Discovery ---
let installedApps = [];

async function fetchInstalledApps() {
  const listEl = document.getElementById("installed-apps-list");
  listEl.innerHTML = '<div style="color: var(--text-dim); padding: 12px;">Scanning installed software on PC...</div>';

  try {
    let data;
    if (fbUrl) {
      const cleanUrl = fbUrl.replace(/\/$/, "");
      const res = await fetch(`${cleanUrl}/focus/installed_apps.json?auth=${fbSecret}`);
      if (res.ok) {
        const json = await res.json();
        data = json?.apps || [];
      }
    } else {
      const res = await apiFetch("/api/installed_apps");
      if (res.ok) {
        const json = await res.json();
        data = json.apps || [];
      }
    }

    if (Array.isArray(data) && data.length > 0) {
      installedApps = data;
      renderInstalledApps();
    } else {
      listEl.innerHTML = '<div style="color: var(--text-dim); padding: 12px;">No installed apps found or scan in progress.</div>';
    }
  } catch (err) {
    listEl.innerHTML = '<div style="color: var(--danger); padding: 12px;">Failed to load installed apps.</div>';
  }
}

function renderInstalledApps(filterQuery = "") {
  const listEl = document.getElementById("installed-apps-list");
  listEl.innerHTML = "";
  const allowedSet = new Set((currentRules.allowed_apps || []).map((a) => a.toLowerCase()));
  const query = filterQuery.toLowerCase().trim();

  const filtered = installedApps.filter((app) => {
    return (
      app.name.toLowerCase().includes(query) ||
      app.exe.toLowerCase().includes(query) ||
      (app.publisher && app.publisher.toLowerCase().includes(query))
    );
  });

  if (filtered.length === 0) {
    listEl.innerHTML = '<div style="color: var(--text-dim); padding: 12px;">No matching applications found.</div>';
    return;
  }

  filtered.forEach((app) => {
    const isAllowed = allowedSet.has(app.exe.toLowerCase());
    const row = document.createElement("div");
    row.className = "app-item-row";
    row.innerHTML = `
      <div class="app-meta">
        <span class="app-name">${app.name}</span>
        <div class="app-details">
          <span class="app-exe">${app.exe}</span>
          <span class="app-publisher">${app.publisher || "Unknown"}</span>
        </div>
      </div>
      <div>
        ${isAllowed
        ? '<span class="badge badge-primary">Allowed</span>'
        : `<button class="btn btn-sm btn-primary btn-allow-app" data-exe="${app.exe}">+ Allow</button>`
      }
      </div>
    `;

    row.querySelector(".btn-allow-app")?.addEventListener("click", async () => {
      await addItem("apps", app.exe);
      renderInstalledApps(document.getElementById("search-installed").value);
    });

    listEl.appendChild(row);
  });
}

document.getElementById("search-installed")?.addEventListener("input", (e) => {
  renderInstalledApps(e.target.value);
});

document.getElementById("btn-refresh-installed")?.addEventListener("click", () => {
  fetchInstalledApps();
});

// Load installed apps when installed tab is clicked
document.querySelector('[data-tab="installed"]')?.addEventListener("click", () => {
  if (installedApps.length === 0) {
    fetchInstalledApps();
  } else {
    renderInstalledApps();
  }
});

// --- 10. Remote App Maintenance & GitHub Sync (1,000 km OTA) ---
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

  try {
    await sendAction("update_app");

    // Poll for update result (up to 20 seconds)
    let attempts = 0;
    const maxAttempts = 10;
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

      if (status && (Date.now() / 1000 - status.timestamp < 30 || attempts >= maxAttempts)) {
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
        updateStatusBadge.textContent = "Request Sent";
      }
    };

    setTimeout(checkUpdate, 2500);
  } catch (err) {
    alert("Failed to send update request: " + err.message);
    btnRemoteUpdate.disabled = false;
    btnRemoteUpdateText.textContent = "Sync & Update App from GitHub";
    updateStatusBadge.style.display = "none";
  }
});

// Auto login if token exists
if (authToken) {
  loginModal.style.display = "none";
  appContainer.style.display = "flex";
  initDashboard();
} else {
  loginModal.style.display = "flex";
  appContainer.style.display = "none";
}

// Initialize Cloud mode indicators
updateCloudModeIndicator();
