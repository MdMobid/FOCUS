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

// Inject Distraction-Free CSS immediately
function injectDistractionFreeStyles() {
  if (document.getElementById("focus-distraction-style")) return;
  const styleEl = document.createElement("style");
  styleEl.id = "focus-distraction-style";
  styleEl.textContent = DISTRACTION_FREE_CSS;
  (document.head || document.documentElement).appendChild(styleEl);
}
injectDistractionFreeStyles();

// Overlay element management
function showBlockOverlay(channelName) {
  let overlay = document.getElementById("focus-yt-block-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "focus-yt-block-overlay";
    overlay.style.cssText = `
      position: fixed;
      top: 0; left: 0; width: 100vw; height: 100vh;
      background: rgba(10, 10, 15, 0.96);
      color: #ffffff;
      z-index: 9999999;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      text-align: center;
      padding: 24px;
    `;
    document.documentElement.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div style="background: #181920; border: 1px solid #2d2f3d; padding: 40px; border-radius: 16px; max-width: 500px; box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
      <div style="font-size: 54px; margin-bottom: 16px;">🔒</div>
      <h2 style="font-size: 24px; margin: 0 0 12px 0; color: #ff5252;">Channel Restricted by Parent</h2>
      <p style="font-size: 15px; color: #a0a4b8; margin: 0 0 20px 0; line-height: 1.5;">
        The channel <strong style="color: #fff;">${channelName || "Unknown"}</strong> is not on your approved study whitelist.
      </p>
      <div style="font-size: 13px; color: #71758c; margin-bottom: 24px;">
        Please ask your parent to approve this channel on the Parent Dashboard if needed.
      </div>
      <button id="focus-back-btn" style="background: #4f46e5; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px;">
        Go to YouTube Home
      </button>
    </div>
  `;

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
  injectDistractionFreeStyles();
  setTimeout(inspectCurrentChannel, 500);
});

// Periodic check for dynamic DOM load
setInterval(inspectCurrentChannel, 1500);
