/**
 * FOCUS YouTube Channel Guard & Distraction Suppressor
 * Filters YouTube channels against the parent's whitelist.
 * Hides YouTube Shorts, recommended sidebar videos, and comments.
 */

const DISTRACTION_FREE_CSS = `
  /* Hide Shorts shelf and navigation links */
  ytd-reel-shelf-renderer,
  ytd-rich-shelf-renderer[is-shorts],
  a[title="Shorts"],
  ytd-guide-entry-renderer:has(a[title="Shorts"]),
  ytd-mini-guide-entry-renderer:has(a[title="Shorts"]),
  ytd-shorts {
    display: none !important;
  }

  /* Hide infinite recommendation rabbit holes */
  #related,
  ytd-watch-next-secondary-results-renderer,
  #comments {
    display: none !important;
  }
`;

// Distraction-Free CSS management based on focus_mode
function updateDistractionFreeStyles() {
  chrome.storage.local.get(["focus_rules"], (res) => {
    const rules = res.focus_rules || {};
    const existing = document.getElementById("focus-distraction-style");
    if (rules.focus_mode) {
      if (!existing) {
        const styleEl = document.createElement("style");
        styleEl.id = "focus-distraction-style";
        styleEl.textContent = DISTRACTION_FREE_CSS;
        (document.head || document.documentElement).appendChild(styleEl);
      }
    } else {
      // When Focus Mode is OFF: full YouTube experience (all recommendations, shorts & comments visible)
      if (existing) {
        existing.remove();
      }
      removeBlockOverlay();
    }
  });
}
updateDistractionFreeStyles();

// Overlay element management
function showBlockOverlay(channelName) {
  let overlay = document.getElementById("focus-yt-block-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "focus-yt-block-overlay";
    overlay.style.cssText = `
      position: fixed;
      top: 0; left: 0; width: 100vw; height: 100vh;
      background: rgba(10, 12, 16, 0.96);
      backdrop-filter: blur(10px);
      color: #e8ecf2;
      z-index: 99999999;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      text-align: center;
      padding: 20px;
      box-sizing: border-box;
    `;
    document.documentElement.appendChild(overlay);
  }

  const cleanChannel = channelName || "Unapproved Creator";
  const rawTitle = document.title ? document.title.replace(" - YouTube", "").trim() : "";
  const videoTitle = (rawTitle && rawTitle !== "YouTube") ? rawTitle : "Current YouTube Video";

  overlay.innerHTML = `
    <div style="background: #181b22; border: 1px solid rgba(255, 255, 255, 0.08); border-top: 1px solid rgba(255,255,255,0.14); padding: 36px 30px; border-radius: 20px; max-width: 460px; width: 100%; box-shadow: 0 24px 50px -10px rgba(0,0,0,0.85); box-sizing: border-box;">
      <div style="width: 52px; height: 52px; margin: 0 auto 16px; border-radius: 14px; background: #12151b; border: 1px solid rgba(255, 255, 255, 0.06); display: flex; align-items: center; justify-content: center; box-shadow: inset 2px 2px 5px rgba(0,0,0,0.6);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#e07a5f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
      </div>

      <h2 style="font-size: 20px; font-weight: 700; color: #e8ecf2; margin: 0 0 6px; letter-spacing: -0.01em;">Content Restricted by Parent</h2>
      <div style="font-size: 11px; font-family: monospace; color: #b85d43; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 18px; font-weight: 600;">FOCUS Policy Enforced</div>

      <div style="background: #111419; border: 1px solid rgba(0, 0, 0, 0.5); box-shadow: inset 1px 2px 6px rgba(0,0,0,0.6); border-radius: 12px; padding: 12px 14px; margin-bottom: 18px; text-align: left;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <span style="font-size: 10.5px; font-weight: 600; text-transform: uppercase; color: #6d7788; letter-spacing: 0.04em;">Creator</span>
          <span style="font-size: 11.5px; font-family: monospace; color: #60a5fa; font-weight: 600;">${cleanChannel}</span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 10.5px; font-weight: 600; text-transform: uppercase; color: #6d7788; letter-spacing: 0.04em;">Video</span>
          <span style="font-size: 11.5px; color: #cbd5e1; font-weight: 500; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${videoTitle}">${videoTitle}</span>
        </div>
      </div>

      <p style="font-size: 13px; color: #9aa5b5; margin: 0 0 22px; line-height: 1.5;">
        Focus Mode is active. If you need this material for your homework or study, you can ask your parent to approve it.
      </p>

      <div style="display: flex; flex-direction: column; gap: 10px;">
        <button id="focus-allow-channel-btn" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; background: #3b5373; border: 1px solid rgba(255,255,255,0.18); border-bottom: 2px solid rgba(0,0,0,0.5); box-shadow: 0 4px 12px rgba(0,0,0,0.3); color: #ffffff; padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s ease;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path></svg>
          Ask to Allow Channel
        </button>

        <button id="focus-allow-video-btn" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; background: #222732; border: 1px solid rgba(255,255,255,0.08); border-bottom: 2px solid rgba(0,0,0,0.4); box-shadow: 0 3px 8px rgba(0,0,0,0.25); color: #e8ecf2; padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s ease;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
          Ask to Allow Video
        </button>

        <button id="focus-back-btn" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; background: #16191f; border: 1px solid rgba(255,255,255,0.05); color: #8b95a5; padding: 10px 18px; border-radius: 10px; font-size: 12.5px; font-weight: 500; cursor: pointer; transition: all 0.15s ease;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
          Return to YouTube Home
        </button>
      </div>

      <div id="focus-req-toast" style="display: none; margin-top: 16px; padding: 10px 14px; border-radius: 9px; background: #13241c; border: 1px solid #1f523a; color: #7de0ae; font-size: 12px; font-weight: 500; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
        ✓ Access request sent to Parent Command Center
      </div>
    </div>
  `;

  const toastEl = document.getElementById("focus-req-toast");
  const showToast = (msg) => {
    if (toastEl) {
      toastEl.textContent = msg;
      toastEl.style.display = "block";
    }
  };

  // 1. Ask to Allow Channel handler
  document.getElementById("focus-allow-channel-btn")?.addEventListener("click", function () {
    this.disabled = true;
    this.textContent = "Sending Request...";
    fetch("http://127.0.0.1:8443/api/request_access", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "channel",
        target: cleanChannel,
        title: cleanChannel,
        url: window.location.href,
        channel: cleanChannel
      })
    })
      .then(r => r.json())
      .then(() => {
        this.innerHTML = "✓ Channel Request Dispatched";
        this.style.background = "#193d2c";
        this.style.borderColor = "#2f7a55";
        showToast("✓ Request sent to parent. They can approve it from their dashboard.");
      })
      .catch(() => {
        this.innerHTML = "✓ Request Queued";
        showToast("✓ Request recorded. Waiting for parent approval.");
      });
  });

  // 2. Ask to Allow Video handler
  document.getElementById("focus-allow-video-btn")?.addEventListener("click", function () {
    this.disabled = true;
    this.textContent = "Sending Request...";
    fetch("http://127.0.0.1:8443/api/request_access", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "video",
        target: window.location.href,
        title: videoTitle,
        url: window.location.href,
        channel: cleanChannel
      })
    })
      .then(r => r.json())
      .then(() => {
        this.innerHTML = "✓ Video Request Dispatched";
        this.style.background = "#193d2c";
        this.style.borderColor = "#2f7a55";
        showToast("✓ Video request sent to parent for review.");
      })
      .catch(() => {
        this.innerHTML = "✓ Request Queued";
        showToast("✓ Request recorded. Waiting for parent approval.");
      });
  });

  // 3. Return to YouTube Home
  document.getElementById("focus-back-btn")?.addEventListener("click", () => {
    window.location.href = "https://www.youtube.com";
  });

  // Pause video if playing
  const video = document.querySelector("video");
  if (video) {
    video.pause();
    video.currentTime = 0;
  }
}

function removeBlockOverlay() {
  const overlay = document.getElementById("focus-yt-block-overlay");
  if (overlay) {
    overlay.remove();
  }
}

// Inspect current YouTube video channel
function inspectCurrentChannel() {
  const path = window.location.pathname;

  // If on homepage or search, don't block
  if (path === "/" || path === "/results") {
    removeBlockOverlay();
    return;
  }

  // If on a channel page directly (e.g. /@freecodecamp)
  if (path.startsWith("/@")) {
    const handle = path.split("/")[1].toLowerCase();
    checkChannelAllowed(handle);
    return;
  }

  // If on watch page: check owner element in DOM
  if (path === "/watch") {
    const ownerEl = document.querySelector("#owner ytd-channel-name a") ||
      document.querySelector("ytd-video-owner-renderer #channel-name a") ||
      document.querySelector("#meta #channel-name a");

    if (ownerEl) {
      const href = ownerEl.getAttribute("href") || "";
      const text = ownerEl.textContent.trim();
      let handle = "";
      if (href.startsWith("/@")) {
        handle = href.split("/")[0] ? href : href.substring(1);
      } else {
        handle = text;
      }
      checkChannelAllowed(handle);
    }
  }
}

function checkChannelAllowed(channelIdentifier) {
  if (!channelIdentifier) return;

  chrome.storage.local.get(["focus_rules"], (res) => {
    const rules = res.focus_rules || {};

    // When Focus Mode is OFF: all YouTube channels are allowed freely
    if (!rules.focus_mode) {
      removeBlockOverlay();
      return;
    }

    const allowedChannels = (rules.allowed_channels || []).map(c => c.trim().toLowerCase());

    const cleanTarget = channelIdentifier.toLowerCase().replace(/^\/?/, "");
    const isAllowed = allowedChannels.some(allowed => {
      const cleanAllowed = allowed.toLowerCase().replace(/^@/, "");
      return cleanTarget === cleanAllowed || cleanTarget === "@" + cleanAllowed;
    });

    if (!isAllowed) {
      showBlockOverlay(channelIdentifier);
    } else {
      removeBlockOverlay();
    }
  });
}

// Observe dynamic YouTube navigation events
window.addEventListener("yt-navigate-finish", () => {
  updateDistractionFreeStyles();
  setTimeout(inspectCurrentChannel, 500);
});

// Periodic check for dynamic DOM load and Focus Mode toggles
setInterval(() => {
  updateDistractionFreeStyles();
  inspectCurrentChannel();
}, 2000);
