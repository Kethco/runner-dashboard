import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import bcrypt
import requests
import uuid
import time
from datetime import datetime, timedelta
import io
import base64
try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False

_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
  <defs>
    <linearGradient id="rwbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1e3a5f"/>
      <stop offset="100%" stop-color="#0891b2"/>
    </linearGradient>
  </defs>
  <rect width="192" height="192" rx="36" fill="url(#rwbg)"/>
  <circle cx="114" cy="42" r="13" fill="white"/>
  <line x1="112" y1="55" x2="98" y2="105" stroke="white" stroke-width="9" stroke-linecap="round"/>
  <line x1="105" y1="74" x2="78" y2="89" stroke="white" stroke-width="7" stroke-linecap="round"/>
  <line x1="105" y1="74" x2="132" y2="62" stroke="white" stroke-width="7" stroke-linecap="round"/>
  <line x1="98" y1="105" x2="75" y2="140" stroke="white" stroke-width="8" stroke-linecap="round"/>
  <line x1="75" y1="140" x2="55" y2="149" stroke="white" stroke-width="7" stroke-linecap="round"/>
  <line x1="98" y1="105" x2="124" y2="132" stroke="white" stroke-width="8" stroke-linecap="round"/>
  <line x1="124" y1="132" x2="144" y2="123" stroke="white" stroke-width="7" stroke-linecap="round"/>
  <polyline points="16,163 40,163 51,147 63,179 75,163 103,163 112,151 120,171 129,163 176,163"
            fill="none" stroke="#38bdf8" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
_ICON_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_ICON_SVG.encode()).decode()


# ── Persistent session store ───────────────────────────────────────────────────
# Sessions are saved to disk so they survive Streamlit server restarts.
# The session token lives in the URL (?t=<token>) and persists across refreshes.

_SESSION_FILE = os.path.join(os.environ.get("DATA_DIR", "artifacts/data"), "sessions.json")
_SESSION_EXPIRY_DAYS = 30


def _load_sessions() -> dict:
    try:
        with open(_SESSION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_sessions(sessions: dict) -> None:
    os.makedirs(os.path.dirname(_SESSION_FILE), exist_ok=True)
    with open(_SESSION_FILE, "w") as f:
        json.dump(sessions, f)


def create_session_token(phone: str, username: str, plan: str, role: str, name: str) -> str:
    token = str(uuid.uuid4())
    sessions = _load_sessions()
    now = time.time()
    # Prune any expired tokens while we're here
    sessions = {k: v for k, v in sessions.items() if v.get("expires", 0) > now}
    sessions[token] = {
        "phone": phone,
        "username": username,
        "plan": plan,
        "role": role,
        "name": name,
        "expires": now + _SESSION_EXPIRY_DAYS * 86400,
    }
    _save_sessions(sessions)
    return token


def validate_session_token(token: str) -> dict | None:
    if not token:
        return None
    sessions = _load_sessions()
    session = sessions.get(token)
    if not session:
        return None
    if session.get("expires", 0) < time.time():
        sessions.pop(token, None)
        _save_sessions(sessions)
        return None
    return session


def delete_session_token(token: str) -> None:
    sessions = _load_sessions()
    sessions.pop(token, None)
    _save_sessions(sessions)


def _is_mobile() -> bool:
    """Return True when the request comes from a mobile/tablet browser."""
    ua = st.context.headers.get("User-Agent", "")
    return any(x in ua for x in ("Mobile", "Android", "iPhone", "iPad", "iPod"))


st.set_page_config(
    page_title="Runner Wellness",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def inject_pwa():
    ua = st.context.headers.get("User-Agent", "")
    is_ios = any(x in ua for x in ("iPhone", "iPad", "iPod"))

    # Shared JS snippet that injects icon + manifest into <head> (runs in both paths)
    _head_injection_js = f"""
    <script>
    (function() {{
      var pw = window.parent;
      var pd = pw.document;
      var head = pd.head;
      var iconUri = '{_ICON_DATA_URI}';

      function addMeta(n, c) {{
        if (pd.querySelector('meta[name="'+n+'"]')) return;
        var m = pd.createElement('meta'); m.name = n; m.content = c; head.appendChild(m);
      }}

      // ── Fix viewport: prevent landscape zoom & lock width to device ──────────
      var vp = pd.querySelector('meta[name="viewport"]');
      var vpContent = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
      if (vp) {{
        vp.setAttribute('content', vpContent);
      }} else {{
        var vpm = pd.createElement('meta');
        vpm.name = 'viewport'; vpm.content = vpContent;
        head.appendChild(vpm);
      }}

      addMeta('theme-color', '#fc4c02');
      addMeta('apple-mobile-web-app-capable', 'yes');
      addMeta('apple-mobile-web-app-status-bar-style', 'black-translucent');
      addMeta('apple-mobile-web-app-title', 'Runner Wellness');

      if (!pd.querySelector('link[rel="apple-touch-icon"]')) {{
        var ico = pd.createElement('link');
        ico.rel = 'apple-touch-icon'; ico.href = iconUri;
        head.appendChild(ico);
      }}
      if (!pd.querySelector('link[rel="icon"]')) {{
        var fav = pd.createElement('link');
        fav.rel = 'icon'; fav.type = 'image/svg+xml'; fav.href = iconUri;
        head.appendChild(fav);
      }}
      if (!pd.querySelector('link[rel="manifest"]')) {{
        var manifest = JSON.stringify({{
          name: 'Runner Wellness',
          short_name: 'Runner Wellness',
          description: 'Daily running check-ins and wellness tracking',
          start_url: '/',
          display: 'standalone',
          background_color: '#0f172a',
          theme_color: '#fc4c02',
          icons: [
            {{src: iconUri, sizes: '192x192', type: 'image/svg+xml'}},
            {{src: iconUri, sizes: '512x512', type: 'image/svg+xml'}}
          ]
        }});
        var blob = new pw.Blob([manifest], {{type: 'application/manifest+json'}});
        var lnk = pd.createElement('link');
        lnk.rel = 'manifest'; lnk.href = pw.URL.createObjectURL(blob);
        head.appendChild(lnk);
      }}

      // ── Block horizontal swipe scrolling (runs once per page load) ──────────
      if (!pw._rwNoHScroll) {{
        pw._rwNoHScroll = true;
        var _tx = 0, _ty = 0;

        // Returns true if el is inside a container that scrolls horizontally on purpose
        function inHScrollBox(el) {{
          while (el && el !== pd.body) {{
            var ov = pw.getComputedStyle(el).overflowX;
            if (ov === 'auto' || ov === 'scroll') return true;
            el = el.parentElement;
          }}
          return false;
        }}

        pd.addEventListener('touchstart', function(e) {{
          _tx = e.touches[0].clientX;
          _ty = e.touches[0].clientY;
        }}, {{passive: true, capture: true}});

        pd.addEventListener('touchmove', function(e) {{
          var dx = Math.abs(e.touches[0].clientX - _tx);
          var dy = Math.abs(e.touches[0].clientY - _ty);
          if (dx > dy && dx > 8 && !inHScrollBox(e.target)) {{
            e.preventDefault();
          }}
        }}, {{passive: false, capture: true}});
      }}
    }})();
    </script>
    """

    # ── iOS: static banner (no JS required for banner) + head injection via iframe ──
    if is_ios:
        st.markdown("""
        <style>
        .rw-ios-banner {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: linear-gradient(135deg, #fc4c02, #c73d00);
            color: white; padding: 13px 16px; z-index: 999999;
            display: flex; align-items: center; gap: 12px;
            box-shadow: 0 -4px 20px rgba(252,76,2,0.35);
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 13px; line-height: 1.45;
        }
        </style>
        <div class="rw-ios-banner" id="rw-ios-banner">
          <div style="font-size:24px;flex-shrink:0;">📲</div>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;font-size:14px;">Install on iPhone</div>
            <div style="opacity:0.93;">
              Open in <strong>Safari</strong> &rarr; tap <strong>Share &#x2197;</strong>
              &rarr; <strong>&ldquo;Add to Home Screen&rdquo;</strong>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        # Inject icon + manifest into <head> even on iOS (iframe executes JS fine)
        components.html(_head_injection_js, height=0)
        # Hide the banner when already running as installed home-screen app
        components.html("""
        <script>
        (function() {
          var pw = window.parent;
          var pd = pw.document;
          var isStandalone = pw.matchMedia('(display-mode: standalone)').matches
                          || (pw.navigator.standalone === true);
          if (isStandalone) {
            var b = pd.getElementById('rw-ios-banner');
            if (b) b.style.setProperty('display', 'none', 'important');
          }
        })();
        </script>
        """, height=0)
        return

    # ── Android / Desktop: JavaScript-powered flow ───────────────────────────
    st.markdown("""
    <style>
    #rw-pwa-banner {
        display: none; position: fixed; bottom: 0; left: 0; right: 0;
        background: linear-gradient(135deg, #fc4c02, #c73d00);
        color: white; padding: 14px 16px; z-index: 999999;
        align-items: center; gap: 12px;
        box-shadow: 0 -4px 20px rgba(252,76,2,0.35);
        font-family: system-ui, -apple-system, sans-serif;
    }
    @media (max-width: 900px) {
        #rw-pwa-banner { display: flex !important; }
        #rw-pwa-banner.rw-hidden { display: none !important; }
    }
    #rw-pwa-install {
        background: white; color: #fc4c02; border: none;
        padding: 9px 18px; border-radius: 24px; font-weight: 700;
        cursor: pointer; white-space: nowrap; font-size: 13px;
        flex-shrink: 0; touch-action: manipulation;
        -webkit-tap-highlight-color: transparent; pointer-events: auto;
    }
    #rw-pwa-dismiss {
        background: transparent; color: rgba(255,255,255,0.85); border: none;
        font-size: 22px; cursor: pointer; margin-left: auto;
        padding: 0 4px; line-height: 1; flex-shrink: 0;
        touch-action: manipulation; -webkit-tap-highlight-color: transparent;
        pointer-events: auto;
    }
    #rw-pwa-instructions {
        display: none; position: fixed; bottom: 0; left: 0; right: 0;
        background: #1a1a2e; color: white; padding: 20px 18px 18px;
        z-index: 1000001; box-shadow: 0 -4px 30px rgba(0,0,0,0.4);
        font-family: system-ui,-apple-system,sans-serif;
    }
    </style>

    <div id="rw-pwa-instructions">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <strong style="font-size:15px;">&#x1F4F2; How to Install</strong>
        <button id="rw-pwa-instr-close"
                style="background:transparent;border:none;color:rgba(255,255,255,0.7);
                       font-size:22px;cursor:pointer;padding:0 4px;
                       touch-action:manipulation;-webkit-tap-highlight-color:transparent;">&#x2715;</button>
      </div>
      <div id="rw-pwa-instr-body" style="font-size:13px;line-height:1.7;"></div>
    </div>

    <div id="rw-pwa-banner">
      <div style="width:36px;height:36px;flex-shrink:0;background:rgba(255,255,255,0.2);
                  border-radius:10px;display:flex;align-items:center;justify-content:center;
                  padding:4px;box-sizing:border-box;">
        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"
             style="width:100%;height:100%;display:block;">
          <circle cx="63" cy="20" r="9" fill="white"/>
          <line x1="60" y1="29" x2="50" y2="52" stroke="white" stroke-width="6" stroke-linecap="round"/>
          <path d="M50 52 L68 68 L60 88" stroke="white" stroke-width="6"
                stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M50 52 L36 65 L44 85" stroke="white" stroke-width="5.5"
                stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M57 37 L42 48" stroke="white" stroke-width="5" stroke-linecap="round"/>
          <path d="M57 37 L72 44" stroke="white" stroke-width="5" stroke-linecap="round"/>
        </svg>
      </div>
      <div style="min-width:0;">
        <div style="font-weight:700;font-size:14px;line-height:1.2;">Add to Home Screen</div>
        <div style="font-size:12px;opacity:0.88;line-height:1.3;">Full-screen app · works offline</div>
      </div>
      <button id="rw-pwa-install">Install App</button>
      <button id="rw-pwa-dismiss" aria-label="Dismiss">&#x2715;</button>
    </div>
    """, unsafe_allow_html=True)

    # Inject icon + manifest into <head> (shared with iOS path above)
    components.html(_head_injection_js, height=0)

    # JavaScript install-prompt logic runs in a real iframe (guaranteed to execute).
    # pw._rwPwaState persists state across iframe recreations.
    components.html("""
    <script>
    (function() {
      var pw = window.parent;
      var pd = pw.document;

      // Persistent state in parent window (survives iframe recreation)
      if (!pw._rwPwaState) {
        pw._rwPwaState = {
          dismissed: false,
          deferredPrompt: null
        };
        // One-time setup
        var DISMISSED_KEY = 'rw-pwa-dismissed-v1';
        pw._rwPwaState.dismissed = pw.localStorage.getItem(DISMISSED_KEY) === '1';

        // Service worker
        if ('serviceWorker' in pw.navigator) {
          pw.navigator.serviceWorker.register('/sw.js', {scope:'/'}).catch(function(){});
        }

        // Capture native install prompt
        pw.addEventListener('beforeinstallprompt', function(e) {
          e.preventDefault();
          pw._rwPwaState.deferredPrompt = e;
          var b = pd.getElementById('rw-pwa-banner');
          if (b) b.classList.remove('rw-hidden');
        });

        // Check standalone
        var isStandalone = pw.matchMedia('(display-mode: standalone)').matches
                        || (pw.navigator.standalone === true);
        if (isStandalone || pw._rwPwaState.dismissed) {
          var b = pd.getElementById('rw-pwa-banner');
          if (b) { b.classList.add('rw-hidden'); b.style.setProperty('display','none','important'); }
        }
      }

      var state = pw._rwPwaState;
      var DISMISSED_KEY = 'rw-pwa-dismissed-v1';

      function hideBanner() {
        var b = pd.getElementById('rw-pwa-banner');
        if (b) { b.classList.add('rw-hidden'); b.style.setProperty('display','none','important'); }
      }
      function showInstr(html) {
        var p = pd.getElementById('rw-pwa-instructions');
        var b = pd.getElementById('rw-pwa-instr-body');
        if (!p || !b) return;
        b.innerHTML = html;
        p.style.display = 'block';
        hideBanner();
      }
      function hideInstr() {
        var p = pd.getElementById('rw-pwa-instructions');
        if (p) p.style.display = 'none';
        if (!state.dismissed) {
          var b = pd.getElementById('rw-pwa-banner');
          if (b) { b.classList.remove('rw-hidden'); b.style.removeProperty('display'); }
        }
      }

      function wireButtons() {
        var install = pd.getElementById('rw-pwa-install');
        var dismiss = pd.getElementById('rw-pwa-dismiss');
        var close   = pd.getElementById('rw-pwa-instr-close');

        if (install && !install._rw) {
          install._rw = true;
          function doInstall(e) {
            e.preventDefault(); e.stopPropagation();
            if (state.deferredPrompt) {
              state.deferredPrompt.prompt();
              state.deferredPrompt.userChoice.then(function(r) {
                state.deferredPrompt = null;
                if (r.outcome === 'accepted') hideBanner();
              });
            } else {
              showInstr(
                '<b>Chrome:</b><br>' +
                '1. Tap the <b>3-dot menu &#x22EE;</b> at the top-right<br>' +
                '2. Tap <b>"Add to Home screen"</b> or <b>"Install app"</b><br><br>' +
                '<b>Samsung Internet:</b><br>' +
                '1. Tap the <b>menu icon &#x2261;</b><br>' +
                '2. Tap <b>"Add page to"</b> &#x2192; <b>"Home screen"</b>'
              );
            }
          }
          install.addEventListener('click', doInstall);
          install.addEventListener('touchend', doInstall);
        }
        if (dismiss && !dismiss._rw) {
          dismiss._rw = true;
          function doDismiss(e) {
            e.preventDefault(); e.stopPropagation();
            pw.localStorage.setItem(DISMISSED_KEY, '1');
            state.dismissed = true;
            hideBanner();
          }
          dismiss.addEventListener('click', doDismiss);
          dismiss.addEventListener('touchend', doDismiss);
        }
        if (close && !close._rw) {
          close._rw = true;
          function doClose(e) { e.preventDefault(); e.stopPropagation(); hideInstr(); }
          close.addEventListener('click', doClose);
          close.addEventListener('touchend', doClose);
        }
      }

      // Wire now (handles first load and iframe recreation)
      wireButtons();

      // Disconnect any old observer and start a fresh one.
      // This ensures the observer survives after Streamlit re-renders recreate
      // the iframe (old observer would have been garbage-collected with old iframe).
      if (pw._rwPwaObserver) { pw._rwPwaObserver.disconnect(); }
      pw._rwPwaObserver = new MutationObserver(wireButtons);
      pw._rwPwaObserver.observe(pd.body, { childList: true, subtree: true });

    })();
    </script>
    """, height=0)


def inject_tab_dock():
    """Inject Icon Dock tab styling via components.html so it overrides emotion CSS."""
    components.html("""
    <script>
    (function() {
      var pw = window.parent;
      var pd = pw.document;

      // ── Inject CSS into parent <head> so it lands after emotion ────────────
      if (!pd.getElementById('rw-dock-style')) {
        var style = pd.createElement('style');
        style.id = 'rw-dock-style';
        style.textContent = [
          '[data-baseweb="tab-list"]{',
            'background:#0d0d1a!important;',
            'border:1px solid rgba(255,255,255,0.07)!important;',
            'border-radius:20px!important;',
            'padding:8px 10px!important;',
            'gap:4px!important;',
            'box-shadow:0 8px 32px rgba(0,0,0,0.5)!important;',
            'overflow:visible!important;}',
          '[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none!important;}',
          'button[data-baseweb="tab"]{',
            'flex-direction:column!important;',
            'align-items:center!important;',
            'justify-content:center!important;',
            'gap:5px!important;',
            'padding:10px 18px!important;',
            'border-radius:14px!important;',
            'border:none!important;',
            'background:transparent!important;',
            'transition:all 0.22s cubic-bezier(0.34,1.56,0.64,1)!important;',
            'min-width:72px!important;',
            'height:auto!important;',
            'position:relative!important;}',
          'button[data-baseweb="tab"]:hover{',
            'background:rgba(255,255,255,0.04)!important;',
            'transform:translateY(-1px)!important;}',
          'button[data-baseweb="tab"][aria-selected="true"]{',
            'background:rgba(252,76,2,0.12)!important;',
            'transform:translateY(-3px) scale(1.04)!important;}',
          '.rw-dock-icon{',
            'width:38px!important;height:38px!important;',
            'border-radius:50%!important;',
            'display:flex!important;',
            'align-items:center!important;justify-content:center!important;',
            'font-size:20px!important;',
            'background:rgba(255,255,255,0.05)!important;',
            'border:1px solid transparent!important;',
            'transition:all 0.2s ease!important;',
            'pointer-events:none!important;box-sizing:border-box!important;}',
          'button[data-baseweb="tab"][aria-selected="true"] .rw-dock-icon{',
            'background:rgba(255,255,255,0.15)!important;}',
          '.rw-dock-label{',
            'font-size:9px!important;font-weight:700!important;',
            'letter-spacing:0.06em!important;text-transform:uppercase!important;',
            'color:rgba(255,255,255,0.35)!important;',
            'transition:color 0.2s ease!important;',
            'font-family:"DM Sans",sans-serif!important;',
            'pointer-events:none!important;white-space:nowrap!important;}',
          'button[data-baseweb="tab"][aria-selected="true"] .rw-dock-label{color:#fc4c02!important;}',
          'button[data-baseweb="tab"].rw-coachz{',
            'background:rgba(252,76,2,0.06)!important;',
            'border:1px solid rgba(252,76,2,0.2)!important;}',
          'button[data-baseweb="tab"].rw-coachz .rw-dock-icon{',
            'background:rgba(252,76,2,0.12)!important;',
            'border:1px solid rgba(252,76,2,0.3)!important;}',
          'button[data-baseweb="tab"].rw-coachz .rw-dock-label{color:rgba(252,76,2,0.7)!important;}',
          'button[data-baseweb="tab"].rw-coachz[aria-selected="true"]{',
            'background:linear-gradient(160deg,#fc4c02,#a83200)!important;',
            'border:none!important;',
            'box-shadow:0 6px 20px rgba(252,76,2,0.5),0 0 0 1px rgba(252,76,2,0.3)!important;}',
          'button[data-baseweb="tab"].rw-coachz[aria-selected="true"] .rw-dock-icon{',
            'background:rgba(255,255,255,0.2)!important;border:1px solid transparent!important;}',
          'button[data-baseweb="tab"].rw-coachz[aria-selected="true"] .rw-dock-label{color:#fff!important;}',
          'button[data-baseweb="tab"].rw-coachz:not([aria-selected="true"])::after{',
            'content:"";position:absolute;top:8px;right:10px;',
            'width:7px;height:7px;border-radius:50%;',
            'background:#fc4c02;box-shadow:0 0 6px rgba(252,76,2,0.8);',
            'animation:rw-cz-dot 2s ease-in-out infinite;}',
          '@keyframes rw-cz-dot{',
            '0%,100%{box-shadow:0 0 6px rgba(252,76,2,0.8);transform:scale(1);}',
            '50%{box-shadow:0 0 14px rgba(252,76,2,1);transform:scale(1.3);}}',
          '@media(max-width:768px){',
            '[data-baseweb="tab-list"]{flex-wrap:wrap!important;overflow-x:hidden!important;',
              'gap:4px!important;padding:6px!important;border-radius:16px!important;}',
            'button[data-baseweb="tab"]{',
              'flex:1 1 calc(33.33% - 8px)!important;',
              'min-width:calc(33.33% - 8px)!important;',
              'max-width:calc(33.33% - 8px)!important;',
              'padding:8px 6px!important;}}'
        ].join('');
        pd.head.appendChild(style);
      }

      // ── Split emoji + label into stacked dock elements ────────────────────
      function applyDock() {
        pd.querySelectorAll('button[data-baseweb="tab"]').forEach(function(btn) {
          if (btn.querySelector('.rw-dock-icon')) {
            if ((btn.textContent || '').indexOf('Coach Z') > -1)
              btn.classList.add('rw-coachz');
            return;
          }
          var raw = btn.textContent.trim();
          if (!raw) return;
          var sp = raw.indexOf(' ');
          if (sp === -1) return;
          var emoji = raw.slice(0, sp);
          var label = raw.slice(sp + 1).trim();

          var icon = pd.createElement('div');
          icon.className = 'rw-dock-icon';
          icon.textContent = emoji;

          var lbl = pd.createElement('div');
          lbl.className = 'rw-dock-label';
          lbl.textContent = label;

          while (btn.firstChild) btn.removeChild(btn.firstChild);
          btn.appendChild(icon);
          btn.appendChild(lbl);

          if (label.indexOf('Coach Z') > -1) btn.classList.add('rw-coachz');
        });
      }

      applyDock();

      if (!pw._rwDockObs) {
        pw._rwDockObs = new pw.MutationObserver(applyDock);
        pw._rwDockObs.observe(pd.body, { childList: true, subtree: true });
      }

      // ── Nav tile buttons ────────────────────────────────────────────────────
      // Remove any old injected style elements (CSS is now rendered by st.markdown)
      ['rw-nav-style', 'rw-nav-style-v2'].forEach(function(id) {
        var el = pd.getElementById(id);
        if (el) el.parentNode.removeChild(el);
      });

      function applyNavTiles() {
        var marker = pd.getElementById('rw-nav-marker');
        if (!marker) return;
        var activeTab  = marker.getAttribute('data-active') || 'dashboard';
        var streak     = marker.getAttribute('data-streak') || '0';
        var lastDate   = marker.getAttribute('data-last-date') || '';
        var hasNotif   = marker.getAttribute('data-has-notif') === '1';

        // Pass 1: detect tab type from raw Streamlit text and persist on element
        pd.querySelectorAll('[data-testid="stButton"] > button').forEach(function(btn) {
          var txt = (btn.textContent || '').trim();
          var isHist = txt.indexOf('History') !== -1;
          var isDash = txt.indexOf('Dashboard') !== -1;
          var isCz   = txt.indexOf('Coach Z') !== -1;
          var isRace = txt.indexOf('Race') !== -1;
          var isExp  = txt.indexOf('Export') !== -1;
          if (isDash || isHist || isCz || isRace || isExp) {
            btn._rwTabId = isDash?'dashboard':isHist?'history':isCz?'coachz':isRace?'race':'export';
          }
          if (txt === 'Sign Out') {
            btn._rwTabId = null;
            btn.classList.add('rw-signout');
            btn.classList.remove('rw-nt');
          }
          // Preserve raw history text before innerHTML replacement
          if (btn._rwTabId === 'history' && !btn._rwHistRaw && !btn.querySelector('.rw-nt-ic')) {
            var histRaw = txt.replace('History','').trim();
            if (histRaw) btn._rwHistRaw = histRaw;
          }
        });

        // Pass 2: style all buttons that have a known tabId
        pd.querySelectorAll('[data-testid="stButton"] > button').forEach(function(btn) {
          var tabId = btn._rwTabId;
          if (!tabId) return;
          var isActive = tabId === activeTab;
          var isCz     = tabId === 'coachz';
          var isHist   = tabId === 'history';
          var isDash   = tabId === 'dashboard';
          var isRace   = tabId === 'race';
          var key = 'v4-' + tabId + (isActive?'1':'0') + streak;
          var classGone = !btn.classList.contains('rw-nt');
          if (btn._rwNtKey === key && !classGone) return;
          btn._rwNtKey = key;

          btn.classList.add('rw-nt');
          if (isActive) btn.classList.add('rw-nt-active'); else btn.classList.remove('rw-nt-active');
          if (isCz)     btn.classList.add('rw-nt-cz');    else btn.classList.remove('rw-nt-cz');
          if (isHist)   btn.classList.add('rw-nt-hist');  else btn.classList.remove('rw-nt-hist');
          if (isDash)   btn.classList.add('rw-nt-dash');  else btn.classList.remove('rw-nt-dash');

          // Build rich inner HTML
          var dot = (isCz && !isActive && hasNotif) ? '<div class="rw-nt-pulse"></div>' : '';
          var iconInner;
          if (isHist) {
            var raw = btn._rwHistRaw || '';
            var pts = raw.split(/\s+/).filter(Boolean);
            var mon = pts[0]||'APR'; var day = pts[1]||'28';
            iconInner = '<span class="rw-nt-month">'+mon+'</span>'
                      + '<span class="rw-nt-day">'+day+'</span>';
          } else {
            var em = isDash?'📊':isCz?'🤖':isRace?'🏅':'📤';
            iconInner = '<span class="rw-nt-icon">'+em+'</span>';
          }

          var extra = '';
          if (isHist) {
            var streakNum = parseInt(streak) || 0;
            var streakTxt = streakNum > 0
              ? '<div class="rw-nt-streak">🔥 '+streakNum+'-day streak</div>'
              : (lastDate ? '<div class="rw-nt-streak">Last '+lastDate+'</div>' : '');
            extra = streakTxt;
          } else if (isCz && !isActive) {
            extra = '<div class="rw-nt-teaser">New training suggestion</div>';
          } else if (isDash && !isActive) {
            extra = '<div class="rw-nt-teaser">View your wellness</div>';
          }

          var lbl = isDash?'DASHBOARD':isHist?'HISTORY':isCz?'COACH Z':isRace?'RACE':'EXPORT';
          btn.innerHTML = dot
            + '<div class="rw-nt-ic">'+iconInner+'</div>'
            + extra
            + '<div class="rw-nt-lbl">'+lbl+'</div>';
        });

        // Force nav rows horizontal — set inline !important styles so Streamlit
        // mobile CSS (which collapses columns) cannot override us.
        pd.querySelectorAll('[data-testid="stButton"] > button.rw-nt').forEach(function(btn) {
          var row = btn.closest('[data-testid="stHorizontalBlock"]');
          if (!row) return;
          if (!row.classList.contains('rw-nav-row')) row.classList.add('rw-nav-row');
          // Inline !important overrides Streamlit's own responsive CSS
          row.style.setProperty('display', 'flex', 'important');
          row.style.setProperty('flex-direction', 'row', 'important');
          row.style.setProperty('flex-wrap', 'nowrap', 'important');
          row.style.setProperty('gap', '8px', 'important');
          row.querySelectorAll('[data-testid="stColumn"]').forEach(function(col) {
            col.style.setProperty('flex', '1 1 0%', 'important');
            col.style.setProperty('min-width', '0', 'important');
            col.style.setProperty('max-width', 'none', 'important');
            col.style.setProperty('width', 'auto', 'important');
            col.style.setProperty('padding-left', '3px', 'important');
            col.style.setProperty('padding-right', '3px', 'important');
          });
        });
      }

      // Debounced wrapper to handle high-frequency class mutations
      var _rwNtTimer = null;
      function applyDebounced() {
        clearTimeout(_rwNtTimer);
        _rwNtTimer = setTimeout(applyNavTiles, 20);
      }

      applyNavTiles();

      // Disconnect any stale observer and create a fresh one that watches BOTH
      // DOM structure changes AND class attribute changes (React wipes className)
      if (pw._rwNavObs) pw._rwNavObs.disconnect();
      pw._rwNavObs = new pw.MutationObserver(applyDebounced);
      pw._rwNavObs.observe(pd.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class']
      });

      // Belt-and-suspenders: re-apply every 200ms regardless (mobile needs fast recovery)
      if (pw._rwNtPoller) clearInterval(pw._rwNtPoller);
      pw._rwNtPoller = setInterval(applyNavTiles, 200);

      // ── Topographic background ─────────────────────────────────────────────
      var _oldTopo = pd.getElementById('rw-topo-bg');
      if (_oldTopo) _oldTopo.parentNode.removeChild(_oldTopo);
      if (!pd.getElementById('rw-topo-v3')) {
        var topoDiv = pd.createElement('div');
        topoDiv.id = 'rw-topo-v3';
        topoDiv.style.cssText = [
          'position:fixed;top:0;left:0;width:100%;height:100%;',
          'z-index:0;pointer-events:none;overflow:hidden;'
        ].join('');
        // Topographic rings centered upper-right (cx≈320, cy≈170)
        var cx = 320, cy = 170;
        var rings = '';
        var rSteps = [
          [45,28],[75,50],[108,76],[145,106],[186,140],
          [230,176],[278,216],[330,260],[386,308],[446,360]
        ];
        rSteps.forEach(function(r, i) {
          rings += '<ellipse cx="'+cx+'" cy="'+cy+'" rx="'+r[0]+'" ry="'+r[1]+'"' +
            ' stroke="#4bc8b8" fill="none" stroke-width="0.65"' +
            ' opacity="'+(0.24 - i*0.018).toFixed(3)+'"/>';
        });
        topoDiv.innerHTML = '<svg viewBox="0 0 390 844" xmlns="http://www.w3.org/2000/svg"' +
          ' style="width:100%;height:100%;" preserveAspectRatio="xMidYMid slice">' +
          // Topographic contour rings
          rings +
          // ── Dynamic runner silhouette ─────────────────────────────────────
          // Glow layer
          '<g stroke="#00e5c0" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.12">' +
          '<circle cx="308" cy="74" r="14" stroke-width="10"/>' +
          '<path d="M308 88 L298 116" stroke-width="10"/>' +
          // torso lean
          '<path d="M298 116 L312 148 L324 180" stroke-width="10"/>' +
          // front leg bent
          '<path d="M298 116 L280 146 L264 174 L258 196" stroke-width="9"/>' +
          // front arm up
          '<path d="M302 100 C288 94 276 86 270 76" stroke-width="8"/>' +
          // back arm down-back
          '<path d="M302 100 C318 106 330 118 336 132" stroke-width="8"/>' +
          '</g>' +
          // Sharp layer
          '<g stroke="#00e5c0" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.72">' +
          '<circle cx="308" cy="74" r="14" stroke-width="1.8"/>' +
          '<path d="M308 88 L298 116" stroke-width="2.4"/>' +
          '<path d="M298 116 L312 148 L324 180" stroke-width="2.4"/>' +
          '<path d="M298 116 L280 146 L264 174 L258 196" stroke-width="2.2"/>' +
          '<path d="M302 100 C288 94 276 86 270 76" stroke-width="2.0"/>' +
          '<path d="M302 100 C318 106 330 118 336 132" stroke-width="2.0"/>' +
          '</g>' +
          '</svg>';
        var stMain = pd.querySelector('[data-testid="stAppViewContainer"]') || pd.body;
        stMain.insertBefore(topoDiv, stMain.firstChild);
      }


      // ── Film-grain noise overlay ───────────────────────────────────────────
      if (!pd.getElementById('rw-grain')) {
        var ns = 'http://www.w3.org/2000/svg';
        var grainSVG = pd.createElementNS(ns, 'svg');
        grainSVG.id = 'rw-grain';
        grainSVG.setAttribute('xmlns', ns);
        grainSVG.setAttribute('width', '300');
        grainSVG.setAttribute('height', '300');
        grainSVG.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
          'z-index:3;pointer-events:none;opacity:0.06;';
        var defs   = pd.createElementNS(ns, 'defs');
        var filter = pd.createElementNS(ns, 'filter');
        filter.setAttribute('id', 'rw-noise-f');
        var turb = pd.createElementNS(ns, 'feTurbulence');
        turb.setAttribute('type', 'fractalNoise');
        turb.setAttribute('baseFrequency', '0.68');
        turb.setAttribute('numOctaves', '4');
        turb.setAttribute('stitchTiles', 'stitch');
        var cm = pd.createElementNS(ns, 'feColorMatrix');
        cm.setAttribute('type', 'saturate');
        cm.setAttribute('values', '0');
        filter.appendChild(turb);
        filter.appendChild(cm);
        defs.appendChild(filter);
        var rect = pd.createElementNS(ns, 'rect');
        rect.setAttribute('width', '100%');
        rect.setAttribute('height', '100%');
        rect.setAttribute('filter', 'url(#rw-noise-f)');
        grainSVG.appendChild(defs);
        grainSVG.appendChild(rect);
        var stMain3 = pd.querySelector('[data-testid="stAppViewContainer"]') || pd.body;
        stMain3.appendChild(grainSVG);
      }
    })();
    </script>
    """, height=0)


DATA_DIR = os.environ.get("DATA_DIR", "artifacts/data")
CHECKINS_FILE = os.path.join(DATA_DIR, "checkins.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
ANALYTICS_FILE = os.path.join(DATA_DIR, "analytics.json")
SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
SLEEP_SCORE = {"Poor": 1, "OK": 2, "Good": 3, "Great": 4}
SLEEP_HOURS = {"Poor": 5.5, "OK": 6.5, "Good": 7.5, "Great": 8.5}
FEELING_SCORE = {"Low": 1, "Fine": 2, "Good": 3, "Great": 4}
SORENESS_SCORE = {"None": 4, "Mild": 3, "Moderate": 2, "High": 1}
READINESS_SCORE = {"No": 1, "Maybe": 2, "Yes": 3}

PLAN_LABELS = {
    "free": "Free",
    "trial": "Free Trial",
    "solo_pro": "Solo Pro ($4.99/mo)",
    "coach_pro": "Coach Starter ($39.99/mo)",
    "coach_starter": "Coach Starter ($39.99/mo)",
    "coach_team": "Coach Team ($79.99/mo)",
    "coach_club": "Coach Club ($149.99/mo)",
}

TRIAL_DAYS = 7

def get_trial_days_remaining(user: dict) -> int:
    trial_start = user.get("trialStartAt")
    if not trial_start:
        return 0
    ms_left = trial_start + TRIAL_DAYS * 24 * 3600 * 1000 - int(datetime.utcnow().timestamp() * 1000)
    return max(0, -(-ms_left // (24 * 3600 * 1000)))  # ceiling division

def is_trial_expired(user: dict) -> bool:
    if user.get("plan") != "trial":
        return False
    return get_trial_days_remaining(user) == 0

st.markdown("""
<style>
/* DM Sans + DM Mono loaded via JS <link> injection — see inject_fonts() call in main() */

/* ═══════════════════════════════════════════════════════════════
   RUNNER WELLNESS — STRAVA-STYLE DARK ATHLETIC THEME
   Primary: #1a1a2e (page)  Card: #16213e  Accent: #fc4c02
   ═══════════════════════════════════════════════════════════════ */

/* Reset & overflow guard */
html {
    overflow-x: clip !important;
    max-width: 100vw !important;
    overscroll-behavior-x: none !important;
}
body {
    overflow-x: hidden !important;
    max-width: 100vw !important;
    overscroll-behavior-x: none !important;
    touch-action: pan-y;
    font-family: 'DM Sans', -apple-system, sans-serif !important;
}
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="block-container"],
section.main > div {
    overflow-x: hidden !important;
    max-width: 100% !important;
}

/* Hide sidebar & Streamlit chrome */
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
button[kind="header"] { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }

/* ── Page background: ultra-deep dark ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: #02050d !important;
}

/* ── Nav tile grid ── */
.rw-nav-grid { display:flex; flex-direction:column; gap:12px; margin:16px 0 20px; }
.rw-nav-row { display:grid; gap:12px; }
.rw-nav-row-3 { grid-template-columns:repeat(3,1fr); }
.rw-nav-row-2 { grid-template-columns:repeat(2,1fr); margin-left:calc(33.33% + 6px); }
.rw-nav-tile {
    background:#0e1726; border:1px solid rgba(255,255,255,0.07); border-radius:22px;
    padding:18px 8px 16px; display:flex; flex-direction:column; align-items:center;
    justify-content:center; gap:8px; cursor:pointer; min-height:112px; position:relative;
    transition:all 0.22s cubic-bezier(0.34,1.56,0.64,1); user-select:none;
    -webkit-tap-highlight-color:transparent;
    text-decoration:none; color:inherit;
}
.rw-nav-tile:active { transform:scale(0.93) !important; }
.rw-nav-tile-active {
    background:linear-gradient(145deg,#e85500 0%,#a32e00 60%,#6b1e00 100%) !important;
    border-color:transparent !important;
    box-shadow:0 10px 32px rgba(232,85,0,0.55),0 0 0 1px rgba(252,76,2,0.25) !important;
}
.rw-nav-tile-coachz {
    background:#0e1726 !important;
    border-color:rgba(252,76,2,0.2) !important;
}
.rw-nav-tile-coachz.rw-nav-tile-active {
    background:linear-gradient(145deg,#fc4c02,#7a1f00) !important;
}
.rw-tile-icon { font-size:46px; line-height:1; filter:drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }
.rw-tile-label {
    font-size:10px; font-weight:800; letter-spacing:0.09em; text-transform:uppercase;
    color:rgba(255,255,255,0.45); font-family:'DM Sans',sans-serif;
}
.rw-nav-tile-active .rw-tile-label { color:rgba(255,255,255,0.9); }
.rw-tile-hist-date {
    display:flex; flex-direction:column; align-items:center; gap:1px;
    background:rgba(255,255,255,0.08); border-radius:12px; padding:6px 10px 8px;
    border:1px solid rgba(255,255,255,0.12);
}
.rw-hist-month { font-size:9px; font-weight:800; letter-spacing:0.12em; color:rgba(255,255,255,0.55); text-transform:uppercase; }
.rw-hist-day { font-size:28px; font-weight:900; color:#fff; line-height:1.05; font-family:'DM Mono','DM Sans',monospace; }
.rw-cz-pulse {
    position:absolute; top:10px; right:10px; width:8px; height:8px;
    border-radius:50%; background:#fc4c02; box-shadow:0 0 8px rgba(252,76,2,0.8);
    animation:rwczp 2s ease-in-out infinite;
}
@keyframes rwczp {
    0%,100%{transform:scale(1);box-shadow:0 0 8px rgba(252,76,2,0.8);}
    50%{transform:scale(1.35);box-shadow:0 0 16px rgba(252,76,2,1);}
}
@media(max-width:768px) {
    .rw-nav-row-2 { margin-left:calc(33.33% + 6px); }
}

/* ── Nav buttons (st.button tiles) ── */
button.rw-nb {
    background:#131929 !important;
    border:1px solid rgba(255,255,255,0.08) !important;
    border-radius:20px !important;
    color:rgba(255,255,255,0.70) !important;
    font-size:12px !important;
    font-weight:700 !important;
    letter-spacing:0.04em !important;
    min-height:80px !important;
    white-space:pre-wrap !important;
    text-align:center !important;
    line-height:1.45 !important;
    display:flex !important;
    flex-direction:column !important;
    align-items:center !important;
    justify-content:center !important;
    padding:12px 6px !important;
    transition:all 0.2s cubic-bezier(0.34,1.56,0.64,1) !important;
    cursor:pointer !important;
    text-decoration:none !important;
    -webkit-tap-highlight-color:transparent !important;
    box-shadow:none !important;
}
button.rw-nb:hover {
    border-color:rgba(252,76,2,0.35) !important;
    background:#1b2336 !important;
    color:rgba(255,255,255,0.9) !important;
    transform:translateY(-2px) !important;
}
button.rw-nb:active { transform:scale(0.94) !important; }
button.rw-nb-active {
    background:linear-gradient(160deg,#fc4c02,#c43a00) !important;
    border-color:transparent !important;
    box-shadow:0 8px 28px rgba(252,76,2,0.45) !important;
    color:#fff !important;
}
button.rw-nb.rw-nb-cz:not(.rw-nb-active) {
    background:rgba(252,76,2,0.07) !important;
    border-color:rgba(252,76,2,0.22) !important;
}
button.rw-nb.rw-nb-cz.rw-nb-active {
    background:linear-gradient(160deg,#fc4c02,#7a1f00) !important;
}

/* ── Brand header ── */
.rw-header {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 9999;
    background: rgba(2,5,13,0.88);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    backdrop-filter: blur(20px) saturate(180%);
    height: 66px;
    display: flex;
    align-items: center;
    padding: 0 22px;
    border-bottom: 1px solid rgba(0,229,192,0.12);
    box-shadow: 0 1px 0 rgba(0,229,192,0.06), 0 4px 24px rgba(0,0,0,0.7);
}
.rw-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px; height: 40px;
    background: linear-gradient(145deg,#ff6120,#c43a00);
    border-radius: 12px;
    margin-right: 12px;
    flex-shrink: 0;
    box-shadow: 0 4px 18px rgba(252,76,2,0.5);
    padding: 5px;
    box-sizing: border-box;
}
.rw-brand {
    font-size: 1.22rem;
    letter-spacing: -0.03em;
    flex: 1;
    font-family: 'DM Sans', sans-serif;
}
.rw-brand-runner {
    font-weight: 800;
    color: #fc4c02;
}
.rw-brand-wellness {
    font-weight: 300;
    color: rgba(255,255,255,0.75);
}
.rw-badge {
    font-size: 0.7rem;
    font-weight: 800;
    padding: 5px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    flex-shrink: 0;
}
.badge-pro           { background: rgba(0,229,192,0.12); color: #00e5c0; border: 1px solid rgba(0,229,192,0.35); }
.badge-coach         { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.35); }
.badge-coach-starter { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.35); }
.badge-coach-team    { background: rgba(109,40,217,0.15); color: #a78bfa; border: 1px solid rgba(109,40,217,0.35); }
.badge-coach-club    { background: rgba(124,58,237,0.15); color: #c4b5fd; border: 1px solid rgba(124,58,237,0.35); }
.badge-athlete       { background: rgba(14,165,233,0.15); color: #38bdf8; border: 1px solid rgba(14,165,233,0.35); }
.badge-trial         { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }
.badge-admin         { background: rgba(252,76,2,0.18);   color: #fc4c02; border: 1px solid rgba(252,76,2,0.45); }
.badge-free          { background: rgba(107,114,128,0.15);color: #9ca3af; border: 1px solid rgba(107,114,128,0.35); }

/* ── Content area ── */
[data-testid="block-container"] {
    padding-top: 80px !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 1200px !important;
}

/* ── Tab navigation — dark pill style ── */
[data-testid="stTabs"] { margin-top: 4px; }
[data-baseweb="tab-list"] {
    background: #080f1e !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 2px !important;
    border-bottom: none !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.5);
    overflow-x: auto !important;
    flex-wrap: nowrap !important;
    -webkit-overflow-scrolling: touch;
}
button[data-baseweb="tab"] {
    border-radius: 9px !important;
    font-size: 0.75rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    padding: 10px 16px !important;
    color: rgba(255,255,255,0.45) !important;
    border: none !important;
    background: transparent !important;
    white-space: nowrap !important;
    min-width: 0 !important;
    transition: all 0.15s ease !important;
    font-family: 'DM Sans', sans-serif !important;
}
button[data-baseweb="tab"]:hover {
    color: rgba(255,255,255,0.8) !important;
    background: rgba(255,255,255,0.06) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: #fc4c02 !important;
    color: #ffffff !important;
    box-shadow: 0 2px 10px rgba(252,76,2,0.4) !important;
}
[data-baseweb="tab-highlight"] { display: none !important; }
[data-baseweb="tab-border"]    { display: none !important; }
[data-testid="stTabsContent"] {
    padding-top: 20px !important;
    border: none !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #0a1422 !important;
    border-radius: 16px;
    padding: 18px 16px !important;
    border: 1px solid rgba(0,229,192,0.1) !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
}
[data-testid="metric-container"] label {
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: rgba(255,255,255,0.4) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    font-family: 'DM Mono', 'DM Sans', monospace !important;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    color: #4ade80 !important;
}

/* ── Card components ── */
.metric-card {
    background: #0a1422;
    border-radius: 16px; padding: 20px;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.07);
    border-left: 4px solid #fc4c02;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
    box-sizing: border-box; width: 100%;
    color: #fff;
}
.alert-card {
    background: rgba(245,158,11,0.1);
    border-radius: 12px; padding: 14px 18px;
    margin-bottom: 10px;
    border: 1px solid rgba(245,158,11,0.25);
    border-left: 5px solid #f59e0b;
    box-sizing: border-box; width: 100%;
    color: #fbbf24;
}
.alert-red {
    background: rgba(239,68,68,0.1);
    border-color: rgba(239,68,68,0.25);
    border-left-color: #ef4444;
    color: #fca5a5;
}
.athlete-card {
    background: #0a1422;
    border-radius: 16px; padding: 18px;
    margin-bottom: 12px;
    border: 1px solid rgba(255,255,255,0.07);
    border-left: 4px solid #fc4c02;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
    box-sizing: border-box; width: 100%;
    color: #fff;
}
.ai-box {
    background: rgba(0,229,192,0.05);
    border-radius: 16px; padding: 22px;
    border: 1px solid rgba(0,229,192,0.18);
    border-left: 4px solid #00e5c0;
    margin: 12px 0;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4), 0 0 24px rgba(0,229,192,0.04);
    box-sizing: border-box; width: 100%;
    color: #fff;
}
.invite-box {
    background: rgba(59,130,246,0.08);
    border-radius: 14px; padding: 20px;
    border: 1px solid rgba(59,130,246,0.2);
    border-left: 4px solid #3b82f6;
    margin: 12px 0;
    font-family: 'DM Mono', monospace; font-size: 0.9rem;
    box-sizing: border-box; width: 100%;
    color: #93c5fd;
}

/* ── Headings ── */
h1 { font-size: 1.6rem !important; font-weight: 800 !important;
     color: #ffffff !important; letter-spacing: -0.02em; margin-bottom: 0 !important; }
h2 { font-size: 1.2rem !important; font-weight: 700 !important; color: rgba(255,255,255,0.85) !important; }
h3 { font-size: 1rem   !important; font-weight: 700 !important; color: rgba(255,255,255,0.7) !important; }

/* General text */
p, li, span, div { color: rgba(255,255,255,0.85); }
.stMarkdown p, .stMarkdown li { color: rgba(255,255,255,0.75) !important; }

/* Forgot-password / forgot-username links on login page */
a.rw-forgot-link,
a.rw-forgot-link:visited,
a.rw-forgot-link:link,
[data-testid="stMarkdown"] a.rw-forgot-link,
[data-testid="stMarkdownContainer"] a.rw-forgot-link,
.stMarkdown a.rw-forgot-link {
    color: #ffffff !important;
    text-decoration: none !important;
    background: none !important;
}
a.rw-forgot-link:hover,
[data-testid="stMarkdown"] a.rw-forgot-link:hover,
.stMarkdown a.rw-forgot-link:hover {
    color: #fc4c02 !important;
    text-decoration: none !important;
}

/* ── Buttons ── */
.stButton > button {
    min-height: 44px; font-size: 0.9rem; font-weight: 700;
    border-radius: 10px; box-sizing: border-box;
    font-family: 'DM Sans', sans-serif !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    background: #fc4c02 !important;
    border-color: #fc4c02 !important;
    color: #fff !important;
    box-shadow: 0 4px 14px rgba(252,76,2,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #e34300 !important;
    border-color: #e34300 !important;
    box-shadow: 0 6px 18px rgba(252,76,2,0.5) !important;
}
.stButton > button:not([kind="primary"]):not(.rw-nt) {
    background: rgba(0,229,192,0.04) !important;
    border: 1px solid rgba(0,229,192,0.38) !important;
    color: rgba(255,255,255,0.82) !important;
    border-radius: 14px !important;
}
.stButton > button:not([kind="primary"]):not(.rw-nt):hover {
    background: rgba(0,229,192,0.08) !important;
    border-color: rgba(0,229,192,0.65) !important;
    color: #fff !important;
    box-shadow: 0 0 16px rgba(0,229,192,0.12) !important;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stSelectbox > div > div {
    min-height: 44px; font-size: 0.95rem;
    background: #0a1422 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #fff !important;
    border-radius: 10px !important;
}
.stTextInput > div > div > input:focus,
.stSelectbox > div > div:focus {
    border-color: #fc4c02 !important;
    box-shadow: 0 0 0 2px rgba(252,76,2,0.2) !important;
}
.stTextInput label, .stSelectbox label, .stTextArea label, .stNumberInput label {
    color: rgba(255,255,255,0.5) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}
.stTextArea > div > div > textarea {
    background: #16213e !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #fff !important;
    border-radius: 10px !important;
}

/* ── Select boxes and dropdowns ── */
[data-baseweb="select"] > div {
    background: #16213e !important;
    border-color: rgba(255,255,255,0.12) !important;
    color: #fff !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] {
    background: #16213e !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
}
[data-baseweb="menu"] li {
    color: rgba(255,255,255,0.8) !important;
}
[data-baseweb="menu"] li:hover {
    background: rgba(252,76,2,0.15) !important;
}

/* ── Tables / DataFrames ── */
[data-testid="stDataFrame"], .dataframe-container {
    overflow-x: auto !important; max-width: 100% !important;
    border-radius: 12px !important;
}
[data-testid="stDataFrame"] table {
    background: #16213e !important;
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stDataFrame"] th {
    background: #0d0d1a !important;
    color: rgba(255,255,255,0.5) !important;
    font-size: 0.72rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
[data-testid="stDataFrame"] tr:hover td {
    background: rgba(252,76,2,0.08) !important;
}

/* ── Charts ── */
.js-plotly-plot, .plotly, .plot-container {
    max-width: 100% !important; overflow: hidden !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #0a1422 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important;
}
[data-testid="stExpander"] summary {
    color: rgba(255,255,255,0.8) !important;
}

/* ── Alerts / info boxes ── */
[data-testid="stAlert"] {
    background: rgba(252,76,2,0.1) !important;
    border: 1px solid rgba(252,76,2,0.25) !important;
    border-radius: 10px !important;
    color: #fbbf24 !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
    background: rgba(59,130,246,0.1) !important;
    border-color: rgba(59,130,246,0.25) !important;
    color: #93c5fd !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
    background: rgba(34,197,94,0.1) !important;
    border-color: rgba(34,197,94,0.25) !important;
    color: #4ade80 !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="error"] {
    background: rgba(239,68,68,0.1) !important;
    border-color: rgba(239,68,68,0.25) !important;
    color: #fca5a5 !important;
}

/* ── Dividers ── */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── Text & images ── */
[data-testid="stMarkdown"] > div {
    max-width: 100% !important; overflow-wrap: break-word !important; word-break: break-word !important;
}
[data-testid="stMarkdown"] img { max-width: 100% !important; height: auto !important; }

/* ── Checkboxes & radios ── */
[data-baseweb="checkbox"] label span { color: rgba(255,255,255,0.8) !important; }
[data-baseweb="radio"] label span { color: rgba(255,255,255,0.8) !important; }

/* ── Sliders ── */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: #fc4c02 !important;
    border-color: #fc4c02 !important;
}

/* ═══ VISUAL ENHANCEMENTS ═══════════════════════════════════════════════════ */


/* ── Film-grain noise overlay ── */
[data-testid="stMain"]::after {
    content: '';
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background-image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='250' height='250'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.68' numOctaves='4' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='250' height='250' filter='url(%23n)'/></svg>");
    background-size: 250px 250px;
    background-repeat: repeat;
    opacity: 0.07;
    pointer-events: none;
    z-index: 5;
}

[data-testid="block-container"] { position: relative; z-index: 1; }

/* ── Micro-animations: metric cards lift on hover ── */
[data-testid="metric-container"] {
    transition: transform 0.22s cubic-bezier(0.34,1.56,0.64,1),
                box-shadow 0.22s ease,
                border-color 0.22s ease !important;
}
[data-testid="metric-container"]:hover {
    transform: translateY(-4px) !important;
    box-shadow: 0 16px 40px rgba(0,0,0,0.55) !important;
    border-color: rgba(252,76,2,0.3) !important;
}

/* ── Micro-animations: custom cards ── */
.metric-card, .athlete-card, .ai-box {
    transition: transform 0.22s cubic-bezier(0.34,1.56,0.64,1),
                box-shadow 0.22s ease !important;
}
.metric-card:hover, .athlete-card:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 14px 36px rgba(0,0,0,0.5) !important;
}

/* ── Button press feedback ── */
.stButton > button {
    transition: all 0.18s ease !important;
}
.stButton > button:active {
    transform: scale(0.96) translateY(1px) !important;
    opacity: 0.88 !important;
}
.stButton > button[kind="primary"]:active {
    box-shadow: 0 2px 8px rgba(252,76,2,0.3) !important;
}

/* ── Icon Dock Tab Bar ── */
[data-baseweb="tab-list"] {
    background: #0d0d1a !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 20px !important;
    padding: 8px 10px !important;
    gap: 4px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5) !important;
    overflow: visible !important;
}
[data-baseweb="tab-highlight"],
[data-baseweb="tab-border"] { display: none !important; }

button[data-baseweb="tab"] {
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 5px !important;
    padding: 10px 18px !important;
    border-radius: 14px !important;
    border: none !important;
    background: transparent !important;
    transition: all 0.22s cubic-bezier(0.34,1.56,0.64,1) !important;
    min-width: 72px !important;
    height: auto !important;
    position: relative !important;
}
button[data-baseweb="tab"]:hover {
    background: rgba(255,255,255,0.04) !important;
    transform: translateY(-1px) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: rgba(252,76,2,0.12) !important;
    transform: translateY(-3px) scale(1.04) !important;
}
.rw-dock-icon {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    background: rgba(255,255,255,0.05);
    border: 1px solid transparent;
    transition: all 0.2s ease;
    pointer-events: none;
}
button[data-baseweb="tab"][aria-selected="true"] .rw-dock-icon {
    background: rgba(255,255,255,0.15) !important;
}
.rw-dock-label {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.35);
    transition: color 0.2s ease;
    font-family: 'DM Sans', sans-serif;
    pointer-events: none;
}
button[data-baseweb="tab"][aria-selected="true"] .rw-dock-label {
    color: #fc4c02 !important;
}

/* ── Coach Z special tile ── */
button[data-baseweb="tab"].rw-coachz {
    background: rgba(252,76,2,0.06) !important;
    border: 1px solid rgba(252,76,2,0.2) !important;
}
button[data-baseweb="tab"].rw-coachz .rw-dock-icon {
    background: rgba(252,76,2,0.12);
    border: 1px solid rgba(252,76,2,0.3);
}
button[data-baseweb="tab"].rw-coachz .rw-dock-label {
    color: rgba(252,76,2,0.7);
}
button[data-baseweb="tab"].rw-coachz[aria-selected="true"] {
    background: linear-gradient(160deg, #fc4c02, #a83200) !important;
    border: none !important;
    box-shadow: 0 6px 20px rgba(252,76,2,0.5), 0 0 0 1px rgba(252,76,2,0.3) !important;
}
button[data-baseweb="tab"].rw-coachz[aria-selected="true"] .rw-dock-icon {
    background: rgba(255,255,255,0.2) !important;
    border: 1px solid transparent !important;
}
button[data-baseweb="tab"].rw-coachz[aria-selected="true"] .rw-dock-label {
    color: #fff !important;
}
button[data-baseweb="tab"].rw-coachz:not([aria-selected="true"])::after {
    content: '';
    position: absolute;
    top: 8px; right: 10px;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #fc4c02;
    box-shadow: 0 0 6px rgba(252,76,2,0.8);
    animation: rw-coachz-dot 2s ease-in-out infinite;
}
@keyframes rw-coachz-dot {
    0%,100% { box-shadow: 0 0 6px rgba(252,76,2,0.8); transform: scale(1); }
    50%      { box-shadow: 0 0 14px rgba(252,76,2,1);  transform: scale(1.3); }
}

/* ── Mobile <= 768px ── */
@media (max-width: 768px) {
    [data-testid="column"],
    [data-testid="stColumn"] {
        width: 100% !important;
        min-width: 100% !important;
        max-width: 100% !important;
        flex: 1 1 100% !important;
    }
    [data-testid="stHorizontalBlock"],
    [data-testid="stColumns"] {
        flex-wrap: wrap !important;
        gap: 0.5rem !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
    }
    [data-testid="block-container"] {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        max-width: 100vw !important;
    }
    [data-testid="stPlotlyChart"],
    .stPlotlyChart, .js-plotly-plot {
        max-width: 100% !important;
        overflow-x: hidden !important;
    }
    [data-baseweb="tab-list"] {
        flex-wrap: wrap !important;
        overflow-x: hidden !important;
        gap: 4px !important;
        padding: 6px !important;
        border-radius: 16px !important;
    }
    button[data-baseweb="tab"] {
        flex: 1 1 calc(33.33% - 8px) !important;
        min-width: calc(33.33% - 8px) !important;
        max-width: calc(33.33% - 8px) !important;
        padding: 8px 6px !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
    h1 { font-size: 1.25rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Running silhouette hero + Coach Z tab glow JS ─────────────────────────
st.markdown("""
<div id="rw-runner-hero" style="
    position:fixed; top:64px; right:0;
    width:240px; height:300px;
    pointer-events:none; z-index:0;
    opacity:0.055;">
  <svg viewBox="0 0 240 300" xmlns="http://www.w3.org/2000/svg"
       style="width:100%;height:100%;">
    <!-- Head -->
    <circle cx="155" cy="42" r="24" fill="white"/>
    <!-- Torso -->
    <path d="M155 66 Q138 105 128 132" stroke="white" stroke-width="13"
          fill="none" stroke-linecap="round"/>
    <!-- Back leg -->
    <path d="M128 132 Q108 162 88 188 Q74 206 96 218"
          stroke="white" stroke-width="11" fill="none" stroke-linecap="round"/>
    <!-- Front leg -->
    <path d="M128 132 Q150 158 170 180 Q184 196 178 222"
          stroke="white" stroke-width="11" fill="none" stroke-linecap="round"/>
    <!-- Back arm -->
    <path d="M142 88 Q112 100 88 106"
          stroke="white" stroke-width="9" fill="none" stroke-linecap="round"/>
    <!-- Front arm -->
    <path d="M152 88 Q178 82 202 70"
          stroke="white" stroke-width="9" fill="none" stroke-linecap="round"/>
    <!-- Motion lines -->
    <line x1="72" y1="106" x2="48" y2="106" stroke="white" stroke-width="4"
          stroke-linecap="round" opacity="0.6"/>
    <line x1="66" y1="122" x2="42" y2="122" stroke="white" stroke-width="3"
          stroke-linecap="round" opacity="0.4"/>
    <line x1="60" y1="138" x2="40" y2="138" stroke="white" stroke-width="2.5"
          stroke-linecap="round" opacity="0.25"/>
  </svg>
</div>

<script>
(function() {
  // ── Icon Dock tabs: split emoji + label, apply Coach Z class ────────────
  function applyCoachZGlow() {
    document.querySelectorAll('button[data-baseweb="tab"]').forEach(function(btn) {
      // If already docked (has our icon div), just ensure Coach Z class
      if (btn.querySelector('.rw-dock-icon')) {
        var txt = btn.textContent || '';
        if (txt.indexOf('Coach Z') > -1) btn.classList.add('rw-coachz');
        return;
      }
      var rawText = btn.textContent.trim();
      if (!rawText) return;
      var spaceIdx = rawText.indexOf(' ');
      if (spaceIdx === -1) return;
      var emoji = rawText.slice(0, spaceIdx);
      var label = rawText.slice(spaceIdx + 1).trim();

      var iconEl = document.createElement('div');
      iconEl.className = 'rw-dock-icon';
      iconEl.textContent = emoji;

      var labelEl = document.createElement('div');
      labelEl.className = 'rw-dock-label';
      labelEl.textContent = label;

      while (btn.firstChild) btn.removeChild(btn.firstChild);
      btn.appendChild(iconEl);
      btn.appendChild(labelEl);

      if (label.indexOf('Coach Z') > -1) btn.classList.add('rw-coachz');
    });
  }

  function applyAll() { applyCoachZGlow(); }
  applyAll();

  if (!window._rwObserver) {
    window._rwObserver = new MutationObserver(applyAll);
    window._rwObserver.observe(document.body, { childList: true, subtree: true });
  }
})();
</script>
""", unsafe_allow_html=True)


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or not _PSYCOPG2_OK:
        return None
    try:
        return psycopg2.connect(db_url)
    except Exception:
        return None


def load_accounts():
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"accounts": {}, "byUsername": {}}


def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f).get("users", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@st.cache_data(ttl=30)
def load_data():
    try:
        with open(CHECKINS_FILE, "r") as f:
            checkins_raw = json.load(f).get("checkins", [])
    except (FileNotFoundError, json.JSONDecodeError):
        checkins_raw = []

    users_raw = load_users()

    if not checkins_raw:
        return pd.DataFrame(), users_raw

    df = pd.DataFrame(checkins_raw)
    df["date"] = pd.to_datetime(df["date"])
    df["sleep_score"] = df["sleep"].map(SLEEP_SCORE).fillna(2)
    df["sleep_hours"] = df["sleep"].map(SLEEP_HOURS).fillna(6.5)
    df["feeling_score"] = df["feeling"].map(FEELING_SCORE).fillna(2)
    df["soreness_score"] = df["soreness"].map(SORENESS_SCORE).fillna(2)
    df["readiness_score"] = df["readiness"].map(READINESS_SCORE).fillna(2)
    df["energy"] = pd.to_numeric(df["energy"], errors="coerce").fillna(3)

    user_names = {phone: u.get("name", phone) for phone, u in users_raw.items()}
    df["name"] = df["phone"].map(user_names).fillna(df["phone"])
    df["is_quick"] = df.get("quick", pd.Series([False] * len(df))).fillna(False)

    return df.sort_values("date"), users_raw


def verify_login(username: str, password: str):
    # ── Admin bypass — username "admin" + ADMIN_PASSWORD env var ──────────────
    if username.strip().lower() == "admin":
        env_admin = os.environ.get("ADMIN_PASSWORD", "admin2024")
        if password == env_admin:
            return {
                "phone": "admin",
                "username": "admin",
                "plan": "admin",
                "role": "admin",
                "name": "Admin",
            }
        return None  # wrong admin password — stop here, don't check regular accounts

    conn = get_db_conn()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT phone, username, password_hash, plan FROM dashboard_accounts "
                "WHERE lower(username)=lower(%s)",
                (username.strip(),),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                try:
                    if bcrypt.checkpw(
                        password.encode("utf-8"),
                        row["password_hash"].encode("utf-8"),
                    ):
                        return dict(row)
                except Exception:
                    pass
                return None
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # Fallback to JSON
    store = load_accounts()
    phone = store.get("byUsername", {}).get(username.lower())
    if not phone:
        return None
    account = store.get("accounts", {}).get(phone)
    if not account:
        return None
    stored_hash = account.get("password_hash", "")
    try:
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return account
    except Exception:
        pass
    return None


def get_athlete_streak(athlete_df: pd.DataFrame) -> int:
    if athlete_df.empty:
        return 0
    dates = sorted(athlete_df["date"].dt.date.unique(), reverse=True)
    return sum(
        1 for j, d in enumerate(dates)
        if d == (datetime.now().date() - timedelta(days=j))
    )


def get_alerts(athletes: dict, df_all: pd.DataFrame, today: pd.Timestamp) -> list:
    alerts = []
    if df_all.empty:
        return alerts
    for phone, athlete in athletes.items():
        aname = athlete.get("name", phone)
        a_df = df_all[df_all["phone"] == phone].copy()
        if a_df.empty:
            continue
        last = a_df.sort_values("date").iloc[-1]
        last_date = last["date"]
        days_ago = (today - last_date).days

        if days_ago >= 3:
            alerts.append({
                "type": "warning",
                "name": aname,
                "phone": phone,
                "msg": f"No check-in for {days_ago} days",
            })
            continue

        energy = last.get("energy", 3)
        soreness = last.get("soreness", "None")
        readiness = last.get("readiness", "Maybe")

        if energy <= 2 and soreness == "High":
            alerts.append({
                "type": "critical",
                "name": aname,
                "phone": phone,
                "msg": f"⚠️ Low energy ({energy}/5) + High soreness — consider rest day",
            })
        elif energy <= 2:
            alerts.append({
                "type": "warning",
                "name": aname,
                "phone": phone,
                "msg": f"Low energy ({energy}/5) — monitor closely",
            })
        elif soreness == "High":
            alerts.append({
                "type": "warning",
                "name": aname,
                "phone": phone,
                "msg": f"High soreness reported — recovery recommended",
            })
        elif readiness == "No":
            alerts.append({
                "type": "warning",
                "name": aname,
                "phone": phone,
                "msg": f"Not feeling ready to train today",
            })
    return alerts


def ai_suggestion(df_runner):
    if df_runner.empty:
        return None
    recent = df_runner.sort_values("date").tail(7)
    avg_energy = recent["energy"].mean()
    avg_soreness_score = recent["soreness_score"].mean()
    last = recent.iloc[-1]

    soreness = last.get("soreness", "None")
    energy = last.get("energy", 3)
    readiness = last.get("readiness", "Maybe")
    sleep = last.get("sleep", "OK")

    if readiness == "No" or (soreness == "High" and energy <= 2):
        return ("🛑 **Rest Day Recommended**\n\n"
                "Showing signs of fatigue. Take a full rest day or do light stretching. "
                "Focus on sleep and nutrition today.")
    elif energy <= 2 or soreness in ("High", "Moderate"):
        return ("🚶 **Easy Recovery Run** — 20–30 min\n\n"
                "Low effort Zone 1–2. Keep heart rate below 70% max. "
                "Promote recovery without adding stress.")
    elif avg_energy >= 4 and avg_soreness_score >= 3 and sleep in ("Good", "Great"):
        return ("⚡ **Quality Session** — Tempo or Intervals\n\n"
                "Consistent energy and low soreness this week. "
                "Great day for 4×1km repeats or a 20-min tempo run.")
    elif energy >= 4 and readiness == "Yes":
        return ("💪 **Moderate Aerobic Run** — 40–50 min\n\n"
                "Good energy — maintain comfortable Zone 2 pace. Great for building base fitness.")
    else:
        return ("🏃 **Easy Aerobic Run** — 30–40 min\n\n"
                "Keep it conversational pace. Consistency beats intensity.")


def show_login_page():
    # Check for hidden admin mode via URL param (?mode=admin)
    params = st.query_params
    admin_mode = params.get("mode", "") == "admin"

    # ── Fullscreen photo slideshow (login page only) ────────────────────────
    st.markdown("""
    <style>
    /* ── Slideshow keyframe ── */
    @keyframes rwSlideKF {
        0%    { opacity: 0; }
        6%    { opacity: 1; }
        28%   { opacity: 1; }
        34%   { opacity: 0; }
        100%  { opacity: 0; }
    }
    .rw-slideshow {
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }
    .rw-slide {
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 100%;
        background-size: cover;
        background-position: center center;
        background-color: #02050d;
        opacity: 0;
        animation: rwSlideKF 36s ease-in-out infinite;
    }
    /* On portrait phones, shift focus to upper portion where the runner is */
    @media (max-width: 768px) and (orientation: portrait) {
        .rw-slide {
            background-size: cover !important;
            background-position: center 20% !important;
        }
        .login-title {
            font-size: 2.8rem !important;
        }
        .login-subtitle {
            font-size: 1.05rem !important;
        }
    }
    /* Stagger each slide by 9s (36s / 4 slides) */
    .rw-slide:nth-child(1) { animation-delay:  0s; }
    .rw-slide:nth-child(2) { animation-delay:  9s; }
    .rw-slide:nth-child(3) { animation-delay: 18s; }
    .rw-slide:nth-child(4) { animation-delay: 27s; }
    </style>
    <div class="rw-slideshow">
      <div class="rw-slide" style="background-image:
        linear-gradient(to bottom, rgba(5,8,20,0.52) 0%, rgba(5,8,20,0.28) 45%, rgba(5,8,20,0.65) 100%),
        url('/app/static/run_235922.jpg');"></div>
      <div class="rw-slide" style="background-image:
        linear-gradient(to bottom, rgba(5,8,20,0.52) 0%, rgba(5,8,20,0.28) 45%, rgba(5,8,20,0.65) 100%),
        url('/app/static/run_1571939.jpg');"></div>
      <div class="rw-slide" style="background-image:
        linear-gradient(to bottom, rgba(5,8,20,0.52) 0%, rgba(5,8,20,0.28) 45%, rgba(5,8,20,0.65) 100%),
        url('/app/static/run_618612.jpg');"></div>
      <div class="rw-slide" style="background-image:
        linear-gradient(to bottom, rgba(5,8,20,0.52) 0%, rgba(5,8,20,0.28) 45%, rgba(5,8,20,0.65) 100%),
        url('/app/static/run_2168292.jpg');"></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    /* Hero section */
    .login-hero {
        text-align: center;
        padding: 48px 20px 24px;
    }
    /* Logo tile — orange */
    .login-logo {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 76px;
        height: 76px;
        background: #fc4c02;
        border-radius: 22px;
        margin-bottom: 18px;
        box-shadow: 0 8px 28px rgba(252,76,2,0.45);
        border: 1.5px solid rgba(255,255,255,0.15);
        padding: 10px;
        box-sizing: border-box;
    }
    .login-title {
        font-size: 2.6rem;
        font-weight: 800;
        margin: 0 0 10px;
        letter-spacing: -0.5px;
        line-height: 1.1;
        text-shadow: 0 2px 16px rgba(0,0,0,0.7);
    }
    .login-title-runner {
        font-weight: 800;
        color: #fc4c02;
    }
    .login-title-wellness {
        font-weight: 300;
        color: rgba(255,255,255,0.85);
    }
    .login-subtitle {
        color: rgba(255,255,255,0.9);
        font-size: 1.1rem;
        font-weight: 500;
        margin: 0;
        text-shadow: 0 1px 10px rgba(0,0,0,0.85);
        letter-spacing: 0.01em;
    }
    /* Strip all wrappers first */
    [data-testid="stTextInput"] > div,
    [data-testid="stTextInput"] > div > div,
    [data-testid="stTextInput"] [data-baseweb="base-input"] {
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        background: transparent !important;
        border-radius: 0 !important;
    }
    /* ── The real box: border + background on [data-baseweb="input"]
       which wraps BOTH the <input> and the eye <button> ── */
    [data-testid="stTextInput"] [data-baseweb="input"] {
        border: none !important;
        border-radius: 12px !important;
        background: #000000 !important;
        overflow: hidden !important;
        box-shadow: none !important;
        outline: none !important;
    }
    [data-testid="stTextInput"]:focus-within [data-baseweb="input"] {
        outline: 2px solid #fc4c02 !important;
        outline-offset: 0px !important;
        box-shadow: none !important;
    }
    /* Kill any browser default focus outlines on children */
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextInput"] button:focus {
        outline: none !important;
        box-shadow: none !important;
    }
    /* Input text — solid black matching the eye button */
    [data-testid="stTextInput"] input {
        border: none !important;
        border-radius: 0 !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        color: #ffffff !important;
        background: #000000 !important;
        outline: none !important;
        box-shadow: none !important;
        padding: 13px 15px !important;
    }
    [data-testid="stTextInput"] input::placeholder { color: rgba(255,255,255,0.32) !important; }
    /* Eye button — deep black background behind the icon */
    [data-testid="stTextInput"] button {
        background: #000000 !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        padding: 0 13px !important;
        color: #ffffff !important;
    }
    [data-testid="stTextInput"] button svg,
    [data-testid="stTextInput"] button svg path {
        fill: #ffffff !important;
        stroke: #ffffff !important;
        color: #ffffff !important;
    }
    /* Labels */
    [data-testid="stTextInput"] label {
        font-weight: 700 !important;
        color: rgba(255,255,255,0.7) !important;
        font-size: 0.82rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.12em !important;
    }
    /* Remove container(border=True) white box */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        border-radius: 0 !important;
    }
    /* Sign In button */
    [data-testid="stButton"] > button[kind="primary"] {
        background: #fc4c02 !important;
        border: none !important;
        border-radius: 9999px !important;
        font-size: 16px !important;
        font-weight: 700 !important;
        padding: 14px !important;
        box-shadow: 0 4px 16px rgba(252,76,2,0.4) !important;
    }
    [data-testid="stButton"] > button[kind="primary"]:hover {
        background: #e34300 !important;
        box-shadow: 0 6px 22px rgba(252,76,2,0.55) !important;
    }
    /* Secondary buttons — hidden (forgot links replaced with <a> tags) */
    [data-testid="stButton"] > button[kind="secondary"] { display: none !important; }
    /* Form column — transparent so background photo shows through */
    section[data-testid="stMain"] [data-testid="column"]:nth-child(2) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 4px !important;
    }
    hr { border-color: rgba(255,255,255,0.08) !important; }
    </style>
    <div class="login-hero">
        <div class="login-logo">
          <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;display:block;">
            <circle cx="63" cy="20" r="9" fill="white"/>
            <line x1="60" y1="29" x2="50" y2="52" stroke="white" stroke-width="6" stroke-linecap="round"/>
            <path d="M50 52 L68 68 L60 88" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            <path d="M50 52 L36 65 L44 85" stroke="white" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            <path d="M57 37 L42 48" stroke="white" stroke-width="5" stroke-linecap="round"/>
            <path d="M57 37 L72 44" stroke="white" stroke-width="5" stroke-linecap="round"/>
          </svg>
        </div>
        <h1 class="login-title">
          <span class="login-title-runner">Runner</span><span class="login-title-wellness"> Wellness</span>
        </h1>
        <p class="login-subtitle">Sign in to view your personal dashboard</p>
    </div>
    """, unsafe_allow_html=True)


    def _api_base():
        domain = (
            os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
            or os.environ.get("REPLIT_DEV_DOMAIN", "")
        )
        return f"https://{domain}" if domain else "http://localhost:8080"

    # initialise reset/recovery state
    if "reset_step" not in st.session_state:
        st.session_state.reset_step = None      # None | "enter_phone" | "enter_code"
    if "username_step" not in st.session_state:
        st.session_state.username_step = None   # None | "enter_phone" | "sent"

    # Handle forgot links arriving via query param
    _forgot = st.query_params.get("_forgot", "")
    if _forgot == "password" and st.session_state.reset_step is None:
        st.session_state.reset_step = "enter_phone"
        del st.query_params["_forgot"]
        st.rerun()
    elif _forgot == "username" and st.session_state.username_step is None:
        st.session_state.username_step = "enter_phone"
        del st.query_params["_forgot"]
        st.rerun()

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center; width:100%; margin:0 0 18px; padding:20px 22px;
                    background:rgba(10,15,40,0.58); border-radius:14px;
                    border:1px solid rgba(255,255,255,0.14);
                    backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);">
            <p style="font-size:16px; font-weight:800; color:#fff; margin:0 0 14px; letter-spacing:-0.01em;">
                Your daily AI coach for runners
            </p>
            <ul style="text-align:left; font-size:14px; color:rgba(255,255,255,0.88); line-height:1.5;
                       padding-left:0; margin:0; display:flex; flex-direction:column; gap:11px;">
                <li style="list-style:none; display:flex; align-items:center; gap:12px;">
                    <span style="font-size:19px; min-width:26px; text-align:center;">🛏</span>
                    <span>5 quick morning check-ins: Sleep, Soreness, Feeling, Energy, Readiness</span>
                </li>
                <li style="list-style:none; display:flex; align-items:center; gap:12px;">
                    <span style="font-size:19px; min-width:26px; text-align:center;">🏆</span>
                    <span>Day 7: 5K / 10K / half predictions + solo workouts</span>
                </li>
                <li style="list-style:none; display:flex; align-items:center; gap:12px;">
                    <span style="font-size:19px; min-width:26px; text-align:center;">👥</span>
                    <span>Coaches: Team Dashboard</span>
                </li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        # ── Normal login ──────────────────────────────────────────────────
        if st.session_state.reset_step is None and st.session_state.username_step is None:
            with st.container():
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                if st.button("Sign In", type="primary", use_container_width=True):
                    if not username or not password:
                        st.error("Please enter your username and password.")
                    else:
                        account = verify_login(username, password)
                        if account:
                            # Role may be embedded in the account dict (admin bypass)
                            # or stored separately in users.json (regular users)
                            if account.get("role"):
                                _role = account["role"]
                                _name = account.get("name", account["username"])
                            else:
                                users_map = load_users()
                                user_rec = users_map.get(account["phone"], {})
                                _role = user_rec.get("role", "runner")
                                _name = user_rec.get("name", account["username"])
                            _plan = account.get("plan", "free")
                            token = create_session_token(
                                account["phone"], account["username"],
                                _plan, _role, _name
                            )
                            st.session_state.logged_in = True
                            st.session_state.phone = account["phone"]
                            st.session_state.username = account["username"]
                            st.session_state.plan = _plan
                            st.session_state.role = _role
                            st.session_state.name = _name
                            st.session_state.session_token = token
                            st.query_params["t"] = token
                            st.rerun()
                        else:
                            st.error("Incorrect username or password. Please try again.")

            st.markdown("""
<div style="display:flex; justify-content:space-between; margin-top:6px; padding:0 2px;">
  <a class="rw-forgot-link" href="?_forgot=username"
     onmouseover="this.style.setProperty('color','#fc4c02','important')"
     onmouseout="this.style.setProperty('color','#ffffff','important')">Forgot username?</a>
  <a class="rw-forgot-link" href="?_forgot=password"
     onmouseover="this.style.setProperty('color','#fc4c02','important')"
     onmouseout="this.style.setProperty('color','#ffffff','important')">Forgot password?</a>
</div>
""", unsafe_allow_html=True)

        # ── Forgot username: enter phone ──────────────────────────────────
        elif st.session_state.username_step == "enter_phone":
            st.markdown(
                "<p style='text-align:center; font-weight:600; margin-bottom:4px;'>"
                "👤 Recover your username</p>"
                "<p style='text-align:center; color:#64748b; font-size:0.85rem;'>"
                "Enter the phone number linked to your account and we'll text you your username.</p>",
                unsafe_allow_html=True,
            )
            with st.container():
                fu_phone = st.text_input(
                    "Phone number",
                    placeholder="+1 555 000 0000",
                    key="fu_phone_input",
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Send Username", type="primary", use_container_width=True):
                        phone_clean = fu_phone.strip().replace(" ", "").replace("-", "")
                        if not phone_clean:
                            st.error("Please enter your phone number.")
                        else:
                            try:
                                requests.post(
                                    f"{_api_base()}/api/auth/forgot-username",
                                    json={"phone": phone_clean},
                                    timeout=10,
                                )
                            except Exception:
                                pass
                            st.success("📱 If that number is registered, your username is on its way!")
                            st.session_state.username_step = "sent"
                            st.rerun()
                with col_b:
                    if st.button("Cancel", use_container_width=True, key="fu_cancel"):
                        st.session_state.username_step = None
                        st.rerun()

        elif st.session_state.username_step == "sent":
            st.success("📱 Check your phone — your username has been sent via SMS.")
            if st.button("Back to sign in", use_container_width=True, type="primary"):
                st.session_state.username_step = None
                st.rerun()

        # ── Reset step 1: enter phone ─────────────────────────────────────
        elif st.session_state.reset_step == "enter_phone":
            st.markdown(
                "<p style='text-align:center; font-weight:600; margin-bottom:4px;'>"
                "🔐 Reset your password</p>"
                "<p style='text-align:center; color:#64748b; font-size:0.85rem;'>"
                "Enter the phone number linked to your account. We'll send a 6-digit SMS code.</p>",
                unsafe_allow_html=True,
            )
            with st.container():
                reset_phone = st.text_input(
                    "Phone number",
                    placeholder="+1 555 000 0000",
                    key="reset_phone_input",
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Send Code", type="primary", use_container_width=True):
                        phone_clean = reset_phone.strip().replace(" ", "").replace("-", "")
                        if not phone_clean:
                            st.error("Please enter your phone number.")
                        else:
                            try:
                                resp = requests.post(
                                    f"{_api_base()}/api/auth/forgot-password",
                                    json={"phone": phone_clean},
                                    timeout=10,
                                )
                                st.session_state["_reset_phone"] = phone_clean
                                st.session_state.reset_step = "enter_code"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not send code. Please try again.")
                with col_b:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state.reset_step = None
                        st.rerun()

        # ── Reset step 2: enter code + new password ───────────────────────
        elif st.session_state.reset_step == "enter_code":
            saved_phone = st.session_state.get("_reset_phone", "")
            st.markdown(
                "<p style='text-align:center; font-weight:600; margin-bottom:4px;'>"
                "📱 Check your phone</p>"
                f"<p style='text-align:center; color:#64748b; font-size:0.85rem;'>"
                f"A 6-digit code was sent to <b>{saved_phone}</b>. Enter it below.</p>",
                unsafe_allow_html=True,
            )
            with st.container():
                code_input = st.text_input(
                    "6-digit code", placeholder="123456", max_chars=6, key="reset_code_input"
                )
                new_pw = st.text_input(
                    "New password", type="password",
                    placeholder="At least 4 characters", key="reset_new_pw"
                )
                new_pw2 = st.text_input(
                    "Confirm new password", type="password",
                    placeholder="Repeat password", key="reset_new_pw2"
                )

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Reset Password", type="primary", use_container_width=True):
                        if not code_input or not new_pw:
                            st.error("Please fill in all fields.")
                        elif new_pw != new_pw2:
                            st.error("Passwords don't match.")
                        elif len(new_pw) < 4:
                            st.error("Password must be at least 4 characters.")
                        else:
                            try:
                                resp = requests.post(
                                    f"{_api_base()}/api/auth/reset-password",
                                    json={
                                        "phone": saved_phone,
                                        "token": code_input.strip(),
                                        "newPassword": new_pw,
                                    },
                                    timeout=10,
                                )
                                if resp.status_code == 200:
                                    st.success("✅ Password reset! You can now sign in.")
                                    st.session_state.reset_step = None
                                    st.session_state.pop("_reset_phone", None)
                                    st.rerun()
                                else:
                                    err = resp.json().get("error", "Invalid or expired code.")
                                    st.error(f"❌ {err}")
                            except Exception:
                                st.error("Could not connect. Please try again.")
                with col_b:
                    if st.button("Cancel", use_container_width=True, key="cancel_code"):
                        st.session_state.reset_step = None
                        st.session_state.pop("_reset_phone", None)
                        st.rerun()

            st.markdown(
                "<p style='text-align:center; color:#94a3b8; font-size:0.8rem; margin-top:6px;'>"
                "Didn't get the code? Check that your phone number matches your account.</p>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        replit_domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0] or os.environ.get("REPLIT_DEV_DOMAIN", "")
        signup_url = f"https://{replit_domain}/api/signup" if replit_domain else "https://runnerwellnessapp.com/api/signup"
        st.markdown(
            f"<p style='text-align:center; color:#888; font-size:0.85rem;'>"
            f"Don't have an account? <a href='{signup_url}' target='_blank' style='color:#22c55e;'>Sign up here</a> — takes 2 minutes."
            f"</p>",
            unsafe_allow_html=True
        )

        _rd = os.environ.get("REPLIT_DOMAINS", "").split(",")[0] or os.environ.get("REPLIT_DEV_DOMAIN", "")
        _base = f"https://{_rd}" if _rd else ""
        st.markdown(
            f"<p style='text-align:center; color:#94a3b8; font-size:0.75rem; margin-top:4px; line-height:2;'>"
            f"By signing in you agree to our "
            f"<a href='{_base}/api/terms' target='_blank' style='color:#10b981; text-decoration:none; font-weight:600;'>Terms of Service</a>"
            f" and "
            f"<a href='{_base}/api/privacy' target='_blank' style='color:#10b981; text-decoration:none; font-weight:600;'>Privacy Policy</a>."
            f"<br>This app is for motivational purposes only — not a medical service.</p>",
            unsafe_allow_html=True,
        )

    # Admin panel — only visible when ?mode=admin is in the URL
    if admin_mode:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("Admin Access", expanded=True):
            admin_pw = st.text_input("Admin password", type="password", key="admin_pw")
            if st.button("Admin Login"):
                env_admin = os.environ.get("ADMIN_PASSWORD", "admin2024")
                if admin_pw == env_admin:
                    st.session_state.logged_in = True
                    st.session_state.phone = None
                    st.session_state.username = "admin"
                    st.session_state.plan = "coach_pro"
                    st.session_state.role = "admin"
                    st.session_state.name = "Admin"
                    st.rerun()
                else:
                    st.error("Invalid admin password.")


def render_header(name: str, plan: str, role: str = "runner"):
    """Fixed brand bar + sign-out button row."""
    badge_map = {
        "admin":     ("Admin",    "badge-admin"),
        "coach_pro":      ("Coach Starter", "badge-coach-starter"),
        "coach_starter":  ("Coach Starter", "badge-coach-starter"),
        "coach_team":     ("Coach Team",    "badge-coach-team"),
        "coach_club":     ("Coach Club",    "badge-coach-club"),
        "athlete":        ("Team Member",   "badge-athlete"),
        "solo_pro":  ("Solo Pro", "badge-pro"),
        "trial":     ("Trial",    "badge-trial"),
    }
    if role == "admin":
        badge_text, badge_cls = "Admin", "badge-admin"
    else:
        badge_text, badge_cls = badge_map.get(plan, (plan.replace("_"," ").title(), "badge-free"))

    st.markdown(
        f'''<div class="rw-header">
            <div class="rw-logo">
              <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;display:block;">
                <circle cx="63" cy="20" r="9" fill="white"/>
                <line x1="60" y1="29" x2="50" y2="52" stroke="white" stroke-width="6" stroke-linecap="round"/>
                <path d="M50 52 L68 68 L60 88" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                <path d="M50 52 L36 65 L44 85" stroke="white" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                <path d="M57 37 L42 48" stroke="white" stroke-width="5" stroke-linecap="round"/>
                <path d="M57 37 L72 44" stroke="white" stroke-width="5" stroke-linecap="round"/>
              </svg>
            </div>
            <div class="rw-brand">
              <span class="rw-brand-runner">Runner</span><span class="rw-brand-wellness"> Wellness</span>
            </div>
            <span class="rw-badge {badge_cls}">{badge_text}</span>
        </div>''',
        unsafe_allow_html=True,
    )

    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo as _ZI
        _hour = _dt.now(_ZI("America/Los_Angeles")).hour
    except Exception:
        _hour = _dt.now().hour
    _greeting = "Good morning" if _hour < 12 else ("Good afternoon" if _hour < 17 else "Good evening")
    _first = name.split()[0] if name else name
    st.markdown(
        f'<div style="padding:22px 0 10px;font-family:DM Sans,sans-serif;">'
        f'<div style="font-size:2.05rem;font-weight:800;color:#ffffff;'
        f'letter-spacing:-0.03em;line-height:1.18;">'
        f'{_greeting},<br>'
        f'<span style="color:#ffffff;">{_first}</span>'
        f' <span style="font-size:1.9rem;">👋</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _render_runner_nav(active: str, runner_df=None):
    """Render large icon-tile navigation grid using st.button (no page reload)."""
    import pandas as _pd
    from datetime import datetime as _dtn, timedelta as _td, date as _d_cls
    try:
        from zoneinfo import ZoneInfo as _ZI
        _today = _dtn.now(_ZI("America/Los_Angeles")).date()
    except Exception:
        _today = _dtn.now().date()

    # ── Compute streak and last check-in from runner_df ──────────────────
    _streak = 0
    _last_date_str = ""
    _last_energy = ""
    if runner_df is not None and not runner_df.empty:
        try:
            _all_dates = sorted(runner_df["date"].dt.date.unique())
            _cur = _today
            for _d in reversed(_all_dates):
                if _d == _cur or _d == _cur - _td(days=1):
                    _streak += 1
                    _cur = _d - _td(days=1)
                elif _d < _cur:
                    break
            if _all_dates:
                _last_date_str = _all_dates[-1].strftime("%b %d")
            _last_energy = int(runner_df["energy"].iloc[-1]) if "energy" in runner_df.columns else 0
        except Exception:
            pass

    # ── Coach Z notification: always show until dismissed ────────────────
    _has_notif = "1"  # always show coach notification dot

    _month_abbr = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
    _m = _month_abbr[_today.month - 1]
    _d_num = _today.day

    # Hidden marker: passes live data to the JS tile styler
    st.markdown(
        f'<div id="rw-nav-marker" data-active="{active}" '
        f'data-streak="{_streak}" data-last-date="{_last_date_str}" '
        f'data-last-energy="{_last_energy}" data-has-notif="{_has_notif}" '
        f'style="display:none;height:0;margin:0;padding:0;"></div>',
        unsafe_allow_html=True,
    )

    # ── Row 1: Dashboard | History | Coach Z ─────────────────────────────
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        if st.button("📊\nDashboard", key="nav_dashboard", use_container_width=True):
            st.session_state["active_tab"] = "dashboard"
            st.rerun()
    with c2:
        if st.button(f"{_m}\n{_d_num}\nHistory", key="nav_history", use_container_width=True):
            st.session_state["active_tab"] = "history"
            st.rerun()
    with c3:
        if st.button("🤖\nCoach Z", key="nav_coachz", use_container_width=True):
            st.session_state["active_tab"] = "coachz"
            st.rerun()

    # ── Row 2: Race | Export (right-aligned) ─────────────────────────────
    _, c4, c5 = st.columns(3, gap="small")
    with c4:
        if st.button("🏅\nRace", key="nav_race", use_container_width=True):
            st.session_state["active_tab"] = "race"
            st.rerun()
    with c5:
        if st.button("📤\nExport", key="nav_export", use_container_width=True):
            st.session_state["active_tab"] = "export"
            st.rerun()



def show_runner_dashboard(phone, name, plan, df_all, users):
    runner_df = df_all[df_all["phone"] == phone].copy() if not df_all.empty else pd.DataFrame()
    user_data = users.get(phone, {})

    render_header(name, plan, "runner")

    # ── Trial / upgrade banner ──
    if plan == "trial":
        _replit_domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0] or os.environ.get("REPLIT_DEV_DOMAIN", "")
        _signup_url = f"https://{_replit_domain}/api/signup" if _replit_domain else "https://runnerwellnessapp.com/api/signup"
        if is_trial_expired(user_data):
            st.markdown(
                f"""<div style='background:linear-gradient(90deg,#7f1d1d,#450a0a);border:1px solid #ef4444;
                border-radius:12px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;gap:12px'>
                <span style='font-size:28px'>⏰</span>
                <div>
                  <b style='color:#fca5a5;font-size:16px'>Your free trial has ended</b><br>
                  <span style='color:#fecaca;font-size:13px'>
                    Upgrade to keep receiving daily SMS check-ins and AI coaching tips.&nbsp;
                    <a href='{_signup_url}' target='_blank'
                       style='color:#f87171;font-weight:700;text-decoration:underline'>Choose a plan →</a>
                  </span>
                </div></div>""",
                unsafe_allow_html=True
            )
        else:
            _days_left = get_trial_days_remaining(user_data)
            st.markdown(
                f"""<div style='background:linear-gradient(90deg,#451a03,#1c0a00);border:1px solid #f59e0b;
                border-radius:12px;padding:12px 18px;margin-bottom:12px;display:flex;align-items:center;gap:12px'>
                <span style='font-size:22px'>🎁</span>
                <div>
                  <b style='color:#fcd34d'>Free Trial — {_days_left} day{"s" if _days_left != 1 else ""} remaining</b><br>
                  <span style='color:#fde68a;font-size:12px'>
                    <a href='{_signup_url}' target='_blank'
                       style='color:#f59e0b;text-decoration:underline'>Upgrade now</a>
                    to keep your check-ins after the trial ends.
                  </span>
                </div></div>""",
                unsafe_allow_html=True
            )

    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = st.query_params.get("tab", "dashboard")
    active = st.session_state["active_tab"]
    _render_runner_nav(active, runner_df)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    if active == "dashboard":
        if runner_df.empty:
            st.markdown(
                '<div style="'
                'background:linear-gradient(135deg,rgba(0,229,192,0.05) 0%,rgba(0,180,150,0.02) 100%);'
                'border:1px solid rgba(0,229,192,0.28);'
                'border-radius:22px;padding:30px 24px 28px;text-align:center;margin:8px 0 20px;'
                'box-shadow:0 0 40px rgba(0,229,192,0.08),0 8px 32px rgba(0,0,0,0.5),'
                'inset 0 1px 0 rgba(0,229,192,0.12);">'
                '<div style="width:48px;height:48px;border-radius:14px;margin:0 auto 14px;'
                'background:rgba(0,229,192,0.1);border:1px solid rgba(0,229,192,0.2);'
                'display:flex;align-items:center;justify-content:center;font-size:24px;">🏃</div>'
                '<p style="color:rgba(255,255,255,0.85);font-size:0.97rem;line-height:1.7;margin:0;'
                'font-family:DM Sans,sans-serif;font-weight:400;letter-spacing:0.01em;">'
                'No check-ins yet! Reply&nbsp;'
                '<strong style="color:#00e5c0;font-weight:800;letter-spacing:0.02em;">YES</strong>'
                '&nbsp;to your morning SMS to get started.'
                '</p></div>',
                unsafe_allow_html=True,
            )
        else:
            total = len(runner_df)
            avg_energy = runner_df["energy"].mean()
            avg_sleep = runner_df["sleep_hours"].mean()
            ready_pct = (runner_df["readiness"] == "Yes").mean() * 100
            last_date = runner_df["date"].max()
            days_since = (datetime.now() - last_date.to_pydatetime()).days

            # ── Readiness Score: weighted 0-100 from latest check-in ──────────
            def _wellness_pct(row):
                sleep_n    = (row["sleep_score"]    - 1) / 3  * 100
                energy_n   = (row["energy"]          - 1) / 4  * 100
                feeling_n  = (row["feeling_score"]   - 1) / 3  * 100
                readiness_n = (row["readiness_score"] - 1) / 2  * 100  # No=0, Maybe=50, Yes=100
                soreness_n = (row["soreness_score"]  - 1) / 3  * 100  # already inverted: None=100
                return min(100, max(0,
                    sleep_n * 0.20 + energy_n * 0.20 + feeling_n * 0.15 +
                    readiness_n * 0.25 + soreness_n * 0.20
                ))

            runner_df["wellness_pct"] = runner_df.apply(_wellness_pct, axis=1)
            today_score = int(round(runner_df["wellness_pct"].iloc[-1]))

            if today_score >= 80:
                score_color, score_bg = "#22c55e", "#16213e"
            elif today_score >= 65:
                score_color, score_bg = "#f59e0b", "#16213e"
            else:
                score_color, score_bg = "#ef4444", "#16213e"

            if today_score >= 80:
                suggestion = "Intervals or tempo run 🔥"
            elif today_score >= 65:
                suggestion = "Easy or steady run 🏃"
            elif today_score >= 45:
                suggestion = "Recovery run or walk 🚶"
            else:
                suggestion = "Rest day — recovery first 🛌"

            # Tomorrow prediction: exponentially weighted recent history + sleep trend
            last7 = runner_df["wellness_pct"].tail(7).tolist()
            raw_weights = [0.05, 0.08, 0.12, 0.15, 0.18, 0.20, 0.22]
            w = raw_weights[-len(last7):]
            w_sum = sum(w)
            tomorrow_raw = sum(s * wi / w_sum for s, wi in zip(last7, w))
            if len(runner_df) >= 4:
                sleep_recent = runner_df["sleep_score"].tail(3).mean()
                sleep_older  = runner_df["sleep_score"].tail(7).head(4).mean()
                tomorrow_raw = min(100, max(0, tomorrow_raw + (sleep_recent - sleep_older) * 4))
            tomorrow_score = int(round(tomorrow_raw))
            t_color = "#22c55e" if tomorrow_score >= 80 else ("#f59e0b" if tomorrow_score >= 65 else "#ef4444")

            circ = 2 * 3.14159265 * 80
            arc  = circ * today_score / 100

            st.markdown(f"""
            <div style="display:flex; flex-direction:column; align-items:center; gap:14px; padding:20px 0 4px;">

              <svg width="200" height="200" viewBox="0 0 200 200" style="overflow:visible">
                <defs>
                  <filter id="rw-glow" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="4" result="blur"/>
                    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                  </filter>
                </defs>
                <circle cx="100" cy="100" r="80" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="14"/>
                <circle cx="100" cy="100" r="80" fill="none" stroke="{score_color}" stroke-width="14"
                        stroke-dasharray="{arc:.2f} {circ:.2f}" stroke-linecap="round"
                        transform="rotate(-90 100 100)" filter="url(#rw-glow)"/>
                <circle cx="100" cy="100" r="65" fill="#1a1a2e"/>
                <text x="100" y="98" text-anchor="middle" dominant-baseline="middle"
                      font-family="system-ui,sans-serif" font-size="46" font-weight="800"
                      fill="{score_color}">{today_score}%</text>
                <text x="100" y="137" text-anchor="middle"
                      font-family="system-ui,sans-serif" font-size="11" font-weight="700"
                      fill="rgba(255,255,255,0.4)" letter-spacing="2">READINESS</text>
              </svg>

              <div style="background:#16213e; border:1.5px solid {score_color}55;
                          border-radius:14px; padding:14px 28px; text-align:center;
                          max-width:340px; width:90%;
                          box-shadow:0 4px 16px rgba(0,0,0,0.3);">
                <p style="margin:0 0 3px; font-size:10px; color:rgba(255,255,255,0.4); font-weight:700;
                           letter-spacing:1.8px; text-transform:uppercase;">Today's Suggestion</p>
                <p style="margin:0; font-size:18px; font-weight:700; color:#ffffff;">{suggestion}</p>
              </div>

              <div style="background:#16213e; border:1.5px solid rgba(255,255,255,0.1);
                          border-radius:14px; padding:12px 28px; text-align:center;
                          max-width:340px; width:90%;
                          box-shadow:0 4px 16px rgba(0,0,0,0.3);">
                <p style="margin:0 0 3px; font-size:10px; color:rgba(255,255,255,0.4); font-weight:700;
                           letter-spacing:1.8px; text-transform:uppercase;">Tomorrow Prediction</p>
                <p style="margin:0; font-size:18px; font-weight:700; color:{t_color};">
                  {tomorrow_score}%
                  <span style="font-size:13px; font-weight:500; color:rgba(255,255,255,0.4);">
                    &nbsp;based on sleep trend
                  </span>
                </p>
              </div>

            </div>
            <hr style="border:none; border-top:1px solid rgba(255,255,255,0.08); margin:20px 0 8px;"/>
            """, unsafe_allow_html=True)
            # ── End Readiness Score widget ─────────────────────────────────────

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Check-ins", total)
            c2.metric("Avg Energy", f"{avg_energy:.1f}/5")
            c3.metric("Avg Sleep", f"{avg_sleep:.1f}hrs")
            c4.metric("Ready to Train", f"{ready_pct:.0f}%")

            if days_since == 0:
                st.success("✅ Checked in today!")
            elif days_since == 1:
                st.info("Yesterday was your last check-in. Keep the streak going!")
            else:
                st.warning(f"Last check-in was {days_since} days ago. Time to get back on track!")

            # ── Streak + Goal race cards ───────────────────────────────────────
            streak = get_athlete_streak(runner_df)
            streak_emoji = "🔥" if streak >= 7 else ("✨" if streak >= 3 else "📅")
            streak_border = "#fcd34d" if streak >= 3 else "rgba(255,255,255,0.1)"
            streak_num_color = "#fcd34d" if streak >= 3 else "rgba(255,255,255,0.5)"
            streak_label_color = "#fbbf24" if streak >= 3 else "rgba(255,255,255,0.35)"

            streak_card = f"""
            <div style="background:#16213e;border:1.5px solid {streak_border};
                        border-radius:16px;padding:16px 18px;text-align:center;flex:1;min-width:120px;
                        box-shadow:0 4px 16px rgba(0,0,0,0.3);">
              <div style="font-size:10px;color:{streak_label_color};font-weight:700;letter-spacing:1.5px;margin-bottom:6px;text-transform:uppercase;">Check-in Streak</div>
              <div style="font-size:32px;font-weight:800;color:{streak_num_color};">{streak_emoji} {streak}</div>
              <div style="font-size:12px;color:rgba(255,255,255,0.35);margin-top:2px;">day{"s" if streak != 1 else ""}</div>
            </div>"""

            goal_card = ""
            goal_dist = user_data.get("goalRaceDistance", "")
            goal_date_str = user_data.get("goalRaceDate", "")
            if goal_dist and goal_date_str:
                try:
                    goal_dt = datetime.strptime(goal_date_str, "%Y-%m-%d")
                    days_left = (goal_dt.date() - datetime.now().date()).days
                    if days_left > 0:
                        weeks = days_left // 7
                        rem = days_left % 7
                        time_str = f"{weeks}w {rem}d" if weeks > 0 else f"{days_left}d"
                        goal_card = f"""
                        <div style="background:#16213e;border:1.5px solid rgba(34,197,94,0.35);
                                    border-radius:16px;padding:16px 18px;text-align:center;flex:1;min-width:140px;
                                    box-shadow:0 4px 16px rgba(0,0,0,0.3);">
                          <div style="font-size:10px;color:rgba(74,222,128,0.7);font-weight:700;letter-spacing:1.5px;margin-bottom:6px;text-transform:uppercase;">Goal Race</div>
                          <div style="font-size:18px;font-weight:700;color:#4ade80;">🎯 {goal_dist}</div>
                          <div style="font-size:15px;font-weight:800;color:#ffffff;">{time_str} to go</div>
                          <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:3px;">{goal_dt.strftime("%-d %b %Y")}</div>
                        </div>"""
                except Exception:
                    pass

            spacer = '<div style="flex:1;min-width:80px"></div>' if not goal_card else ""
            st.markdown(f"""
            <div style="display:flex;gap:12px;margin:14px 0 8px;flex-wrap:wrap;">
              {streak_card}
              {goal_card or spacer}
            </div>""", unsafe_allow_html=True)

            # ── Injury prevention alert ────────────────────────────────────────
            if not runner_df.empty:
                recent_ci = runner_df.sort_values("date", ascending=False).head(5)
                last3 = recent_ci.head(3)
                last2 = recent_ci.head(2)
                high_sor3 = int(last3["soreness"].isin(["High", "Moderate"]).sum())
                no_ready2 = int((last2["readiness"] == "No").sum())
                top = recent_ci.iloc[0]
                if len(last3) == 3 and high_sor3 == 3:
                    st.error("⚠️ **Injury Alert** — You've had moderate/high soreness 3 days in a row. Consider a rest or easy recovery day today to prevent a longer setback.")
                elif len(last2) == 2 and no_ready2 == 2:
                    st.warning("⚠️ **Readiness Drop** — You've felt not ready to train 2 days in a row. Focus on sleep, nutrition and recovery today.")
                elif top["soreness"] == "High" and top["readiness"] == "No":
                    st.warning("⚠️ High soreness + low readiness today. A rest day is the smart choice right now.")

            st.markdown("---")
            last_30 = runner_df[runner_df["date"] >= pd.Timestamp(datetime.now() - timedelta(days=30))]
            if last_30.empty:
                last_30 = runner_df.tail(10)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=last_30["date"], y=last_30["energy"],
                mode="lines+markers", name="Energy (1–5)",
                line=dict(color="#22c55e", width=2), marker=dict(size=7)
            ))
            fig.add_trace(go.Scatter(
                x=last_30["date"], y=last_30["sleep_score"],
                mode="lines+markers", name="Sleep Quality (1–4)",
                line=dict(color="#128c7e", width=2, dash="dot"), marker=dict(size=7)
            ))
            fig.update_layout(
                title="Energy & Sleep — Last 30 Days",
                xaxis_title="Date", yaxis_title="Score",
                hovermode="x unified", height=360,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                plot_bgcolor="#16213e", paper_bgcolor="#16213e",
                font=dict(color='rgba(255,255,255,0.7)', family="system-ui, sans-serif"),
            )
            st.plotly_chart(fig, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                soreness_counts = runner_df["soreness"].value_counts().reset_index()
                soreness_counts.columns = ["Soreness", "Count"]
                order_s = ["None", "Mild", "Moderate", "High"]
                color_s = {"None": "#22c55e", "Mild": "#8bc34a", "Moderate": "#ffc107", "High": "#dc3545"}
                soreness_counts = soreness_counts.set_index("Soreness").reindex(order_s).dropna().reset_index()
                fig_s = px.bar(soreness_counts, x="Soreness", y="Count",
                               color="Soreness", color_discrete_map=color_s,
                               title="Soreness Distribution", text="Count")
                fig_s.update_traces(textposition="outside")
                fig_s.update_layout(showlegend=False, height=300, plot_bgcolor="#16213e", paper_bgcolor="#16213e", font=dict(color='rgba(255,255,255,0.7)'))
                st.plotly_chart(fig_s, use_container_width=True)

            with col_b:
                readiness_counts = runner_df["readiness"].value_counts().reset_index()
                readiness_counts.columns = ["Readiness", "Count"]
                order_r = ["Yes", "Maybe", "No"]
                color_r = {"Yes": "#22c55e", "Maybe": "#ffc107", "No": "#dc3545"}
                readiness_counts = readiness_counts.set_index("Readiness").reindex(order_r).dropna().reset_index()
                fig_r = px.pie(readiness_counts, names="Readiness", values="Count",
                               color="Readiness", color_discrete_map=color_r,
                               title="Readiness Breakdown")
                fig_r.update_layout(height=300, paper_bgcolor="#16213e", font=dict(color='rgba(255,255,255,0.7)'))
                st.plotly_chart(fig_r, use_container_width=True)

    # ── History ───────────────────────────────────────────────────────────────
    elif active == "history":
        if runner_df.empty:
            st.info("No check-ins yet. Reply YES to your morning SMS to start!")
        else:
            col1, col2 = st.columns(2)
            with col1:
                date_from = st.date_input("From", value=datetime.now() - timedelta(days=30))
            with col2:
                date_to = st.date_input("To", value=datetime.now())

            filtered = runner_df[
                (runner_df["date"] >= pd.Timestamp(date_from)) &
                (runner_df["date"] <= pd.Timestamp(date_to))
            ].copy()

            st.markdown(f"**{len(filtered)} check-ins** in selected range")

            display = filtered[["date", "sleep", "feeling", "energy", "soreness", "readiness"]].copy()
            display.columns = ["Date", "Sleep", "Feeling", "Energy", "Soreness", "Readiness"]
            display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
            display = display.sort_values("Date", ascending=False)

            def color_readiness(val):
                c = {"Yes": "background-color: #d4edda", "No": "background-color: #f8d7da",
                     "Maybe": "background-color: #fff3cd"}
                return c.get(val, "")

            def color_energy(val):
                if val >= 4:
                    return "background-color: #d4edda"
                elif val <= 2:
                    return "background-color: #f8d7da"
                return ""

            styled = display.style.map(color_readiness, subset=["Readiness"]).map(color_energy, subset=["Energy"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Coach Z ───────────────────────────────────────────────────────────────
    elif active == "coachz":
        st.markdown("*Based on your recent check-in data*")
        if runner_df.empty:
            st.info("No check-ins yet! Reply YES to your morning SMS to get personalised suggestions.")
        else:
            suggestion = ai_suggestion(runner_df)
            if suggestion:
                st.markdown(f"""
                <div class="ai-box">
                    <h4 style="margin-top:0; color:#166534;">Today\'s Recommendation</h4>
                    {suggestion.replace(chr(10), "<br>")}
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### Your Recent Trends (7 days)")

            last_7 = runner_df.tail(7)
            if not last_7.empty:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Avg Energy", f"{last_7['energy'].mean():.1f}/5")
                c2.metric("Avg Sleep", f"{last_7['sleep_hours'].mean():.1f}hrs")
                soreness_map = {"None": 0, "Mild": 1, "Moderate": 2, "High": 3}
                avg_soreness_num = last_7["soreness"].map(soreness_map).mean()
                soreness_labels = ["None", "Mild", "Moderate", "High"]
                avg_soreness_label = soreness_labels[round(avg_soreness_num)] if pd.notna(avg_soreness_num) else "N/A"
                c3.metric("Avg Soreness", avg_soreness_label)
                c4.metric("Ready to Train", f"{(last_7['readiness'] == 'Yes').sum()}/7 days")

            st.markdown("---")
            st.info("💡 Complete a morning SMS check-in to unlock personalised AI coaching tips.")

    # ── Race ──────────────────────────────────────────────────────────────────
    elif active == "race":
        st.markdown("### 🏅 Race Predictor")
        st.markdown("*Research-backed VO₂max model · Daniels VDOT race tables*")

        def predict_vo2max_py(df, gender):
            last7 = df.tail(7)
            energy_avg = (last7["energy"] * 2).mean()
            sleep_avg = last7["sleep_hours"].mean()
            soreness_map = {"None": 0, "Mild": 1, "Moderate": 2, "High": 3}
            soreness_avg = last7["soreness"].map(soreness_map).mean()
            gender_bonus = 9 if gender == "M" else 0
            vo2 = 45 + gender_bonus - 0.14 * soreness_avg * 10 + 0.67 * sleep_avg + 1.2 * energy_avg
            return max(30.0, min(75.0, vo2))

        def vo2_to_race(vo2, dist):
            if dist == "5k":   return (300 / (vo2 * 0.85 + 5)) * 60
            if dist == "10k":  return (300 / (vo2 * 0.82 + 4)) * 60
            return (300 / (vo2 * 0.78 + 3)) * 60

        def fmt_time(minutes):
            total = round(minutes * 60)
            return f"{total // 60}:{(total % 60):02d}"

        if runner_df.empty or len(runner_df) < 7:
            checkin_count = len(runner_df) if not runner_df.empty else 0
            st.info(
                f"You need at least **7 check-ins** for accurate VO₂max predictions. "
                f"You have **{checkin_count}** so far — keep checking in daily!"
            )
            st.markdown(
                "Once you have 7 check-ins, your 5K, 10K and Half Marathon predictions "
                "will appear here, updated every Sunday via SMS too.  \n"
                "You can also text **LOG** anytime to log a workout — "
                "predictions based on your actual times will appear below."
            )
        else:
            saved_gender = user_data.get("gender", "M")
            gender_idx = 0 if saved_gender == "M" else 1
            gender_choice = st.radio(
                "Gender (used in VO₂max estimate)",
                ["M — Male", "F — Female"],
                index=gender_idx,
                horizontal=True,
            )
            gender = "M" if gender_choice.startswith("M") else "F"

            vo2 = predict_vo2max_py(runner_df, gender)
            t5k   = fmt_time(vo2_to_race(vo2, "5k"))
            t10k  = fmt_time(vo2_to_race(vo2, "10k"))
            thalf = fmt_time(vo2_to_race(vo2, "half"))

            baseline_min = user_data.get("baseline5kMin")

            st.markdown("---")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Est. VO₂max", f"{vo2:.1f}", "ml/kg/min")

            if baseline_min:
                pred_5k_min = vo2_to_race(vo2, "5k")
                diff_sec = round((baseline_min - pred_5k_min) * 60)
                if diff_sec > 0:
                    delta_label = f"+{diff_sec}s faster than baseline"
                elif diff_sec < 0:
                    delta_label = f"{abs(diff_sec)}s slower than baseline"
                else:
                    delta_label = "matches baseline"
                c2.metric("🏃 5K (predicted)", t5k, delta_label,
                          delta_color="normal" if diff_sec >= 0 else "inverse")
                c3.metric("📌 5K Baseline", fmt_time(baseline_min))
                c4.metric("🏃 Half Marathon", thalf)
                faster = diff_sec > 0
                st.info(
                    f"Your predicted 5K ({t5k}) vs your baseline ({fmt_time(baseline_min)}) — "
                    + ("you're on track to go faster! 🚀" if faster
                       else "keep pushing those check-ins to close the gap! 💪")
                )
            else:
                c2.metric("🏃 5K", t5k, "±20s")
                c3.metric("🏃 10K", t10k)
                c4.metric("🏃 Half Marathon", thalf)

            # ── VO₂max trend over rolling 7-day windows ──────────────────────
            if len(runner_df) >= 7:
                st.markdown("---")
                st.markdown("#### VO₂max Trend")
                rows = []
                for i in range(6, len(runner_df)):
                    window = runner_df.iloc[i - 6: i + 1]
                    v = predict_vo2max_py(window, gender)
                    rows.append({"date": runner_df.iloc[i]["date"], "vo2max": round(v, 2)})
                trend_df = pd.DataFrame(rows)
                fig_v = go.Figure()
                fig_v.add_trace(go.Scatter(
                    x=trend_df["date"], y=trend_df["vo2max"],
                    mode="lines+markers", name="VO₂max",
                    line=dict(color="#fc4c02", width=2.5),
                    marker=dict(size=7),
                    fill="tozeroy",
                    fillcolor="rgba(252,76,2,0.08)",
                ))
                fig_v.update_layout(
                    xaxis_title="Date", yaxis_title="VO₂max (ml/kg/min)",
                    yaxis=dict(range=[max(25, trend_df["vo2max"].min() - 5),
                                      min(80, trend_df["vo2max"].max() + 5)]),
                    hovermode="x unified", height=300,
                    plot_bgcolor="#16213e", paper_bgcolor="#16213e",
                    font=dict(color='rgba(255,255,255,0.7)', family="system-ui, sans-serif"),
                )
                st.plotly_chart(fig_v, use_container_width=True)

            st.markdown("---")
            st.caption(
                "Predictions use a VO₂max model (r=0.78 correlation) from running research, "
                "combined with Daniels VDOT race pace tables. Based on your last 7 check-ins. "
                "For best accuracy, check in every day. "
                "Race predictions are also sent automatically every Sunday at 8 AM."
            )

        # ── Riegel workout-based predictions ──────────────────────────────────
        st.markdown("---")
        st.markdown("### 🏃 Predictions from Your Logged Workouts")
        st.markdown("*Riegel endurance formula — predicts your time at any distance from a logged performance*")

        _DIST_M = {
            "100m": 100, "200m": 200, "400m": 400, "800m": 800, "1500m": 1500, "Mile": 1609,
            "5K": 5000, "8K": 8000, "10K": 10000, "15K": 15000,
            "Half Marathon": 21097.5, "Marathon": 42195,
        }
        _TRACK_LIST = ["100m", "200m", "400m", "800m", "1500m", "Mile"]
        _ROAD_LIST  = ["5K", "8K", "10K", "15K", "Half Marathon", "Marathon"]

        def _riegel(b_m, b_s, t_m):
            return b_s * (t_m / b_m) ** 1.06

        def _fmt_rt(secs):
            s = float(secs)
            if s < 60:
                return f"{s:.2f}s"
            if s < 3600:
                m = int(s // 60); r = s % 60
                return f"{m}:{int(r):02d}"
            h = int(s // 3600); m = int((s % 3600) // 60); r = int(s % 60)
            return f"{h}:{m:02d}:{r:02d}"

        def _pred_table(dist_list, best_times):
            rows = []
            for tgt in dist_list:
                tm = _DIST_M.get(tgt)
                if not tm:
                    continue
                if tgt in best_times:
                    rows.append({"Distance": tgt, "Time": _fmt_rt(best_times[tgt]), "": "✅ Logged"})
                else:
                    preds = [_riegel(_DIST_M[b], bt, tm) for b, bt in best_times.items() if b in _DIST_M]
                    if preds:
                        med = sorted(preds)[len(preds) // 2]
                        rows.append({"Distance": tgt, "Time": _fmt_rt(med), "": "Predicted"})
            return pd.DataFrame(rows) if rows else None

        try:
            with open(CHECKINS_FILE, "r") as _wf:
                _raw_w = json.load(_wf).get("workouts", [])
            _user_workouts = [w for w in _raw_w if w.get("phone") == phone and w.get("timeSeconds")]
        except (FileNotFoundError, json.JSONDecodeError):
            _user_workouts = []

        if not _user_workouts:
            st.info("No logged workouts yet. Text **LOG** to your coach bot to log a run and unlock predictions here.")
        else:
            _best = {}
            for _w in _user_workouts:
                _ev = _w.get("event") or _w.get("distance")
                _ts = _w.get("timeSeconds")
                if _ev and _ts and _ev in _DIST_M:
                    if _ev not in _best or _ts < _best[_ev]:
                        _best[_ev] = _ts

            _track_best = {k: v for k, v in _best.items() if k in _TRACK_LIST}
            _road_best  = {k: v for k, v in _best.items() if k in _ROAD_LIST}
            _aero_track = {k: v for k, v in _track_best.items() if k in ["800m", "1500m", "Mile"]}

            _col1, _col2 = st.columns(2)

            if _track_best:
                with _col1:
                    st.markdown("#### 🏟️ Track Events")
                    _aero_road = {k: v for k, v in _road_best.items() if k in ["5K", "8K", "10K"]}
                    _track_preds = _pred_table(_TRACK_LIST, {**_track_best, **_aero_road})
                    if _track_preds is not None:
                        st.dataframe(_track_preds, use_container_width=True, hide_index=True)

            if _road_best or _aero_track:
                with _col2:
                    st.markdown("#### 🛣️ Road Races")
                    _road_preds = _pred_table(_ROAD_LIST, {**_road_best, **_aero_track})
                    if _road_preds is not None:
                        st.dataframe(_road_preds, use_container_width=True, hide_index=True)

            _n = len(_user_workouts)
            st.caption(
                f"Based on {_n} logged workout{'s' if _n != 1 else ''}. "
                "Riegel formula is most reliable for distances 1500m and above — "
                "sprint predictions (100m, 200m) are estimates. "
                "Text **LOG** to add more workouts and improve accuracy."
            )

    # ── Export ────────────────────────────────────────────────────────────────
    elif active == "export":
        if runner_df.empty:
            st.info("No data to export yet.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                date_from = st.date_input("From date", value=datetime.now() - timedelta(days=90))
            with col2:
                date_to = st.date_input("To date", value=datetime.now())

            export_df = runner_df[
                (runner_df["date"] >= pd.Timestamp(date_from)) &
                (runner_df["date"] <= pd.Timestamp(date_to))
            ][["date", "sleep", "feeling", "energy", "soreness", "readiness"]].copy()
            export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
            export_df = export_df.sort_values("date", ascending=False)

            st.markdown(f"**{len(export_df)} records** ready to export.")
            st.dataframe(export_df, use_container_width=True, hide_index=True)

            csv_buffer = io.StringIO()
            export_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv_buffer.getvalue().encode("utf-8"),
                file_name=f"my_checkins_{date_from}_{date_to}.csv",
                mime="text/csv",
                type="primary",
            )


def show_coach_dashboard(coach_phone, name, plan, df_all, users):
    render_header(name, plan, "coach")

    athletes = {
        phone: u
        for phone, u in users.items()
        if u.get("coachPhone") == coach_phone
    } if coach_phone else {}

    today = pd.Timestamp(datetime.now().date())

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["👥 Team", "📈 Trends", "📊 Analytics", "📨 Invite", "📤 Export"]
    )

    # ── Tab 1: Team Overview ──────────────────────────────────────────────────
    with tab1:
        col_title, col_refresh = st.columns([5, 1])
        with col_refresh:
            if st.button("🔄 Refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        if not athletes:
            st.info("No athletes linked yet. Use the **Invite** tab to send them a personalised signup link.")
        else:
            alerts = get_alerts(athletes, df_all, today)
            if alerts:
                st.markdown(f"### 🚨 Alerts ({len(alerts)})")
                for alert in alerts:
                    css_class = "alert-card alert-red" if alert["type"] == "critical" else "alert-card"
                    icon = "🔴" if alert["type"] == "critical" else "🟡"
                    st.markdown(
                        f'<div class="{css_class}"><strong>{icon} {alert["name"]}</strong> — {alert["msg"]}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("")

            st.markdown("### Team Roster")

            rows = []
            for phone, athlete in athletes.items():
                athlete_df = df_all[df_all["phone"] == phone].copy() if not df_all.empty else pd.DataFrame()
                aname = athlete.get("name", phone)

                if athlete_df.empty:
                    rows.append({
                        "Athlete": aname, "Energy": "—", "Sleep": "—",
                        "Soreness": "—", "Readiness": "—",
                        "Last Check-in": "Never", "Streak 🔥": 0, "Status": "⚪ No data",
                    })
                    continue

                last = athlete_df.sort_values("date").iloc[-1]
                last_date = last["date"]
                days_ago = (today - last_date).days
                streak = get_athlete_streak(athlete_df)

                if days_ago == 0:
                    status = "🟢 Today"
                elif days_ago == 1:
                    status = "🟡 Yesterday"
                elif days_ago <= 2:
                    status = f"🟡 {days_ago}d ago"
                else:
                    status = f"🔴 {days_ago}d ago"

                rows.append({
                    "Athlete": aname,
                    "Energy": f"{int(last['energy'])}/5",
                    "Sleep": last.get("sleep", "—"),
                    "Soreness": last.get("soreness", "—"),
                    "Readiness": last.get("readiness", "—"),
                    "Last Check-in": last_date.strftime("%b %d"),
                    "Streak 🔥": streak,
                    "Status": status,
                })

            roster_df = pd.DataFrame(rows)

            def color_row(row):
                styles = [""] * len(row)
                idx = roster_df.columns.tolist()
                energy_val = row["Energy"]
                soreness_val = row["Soreness"]
                readiness_val = row["Readiness"]

                energy_num = int(energy_val.split("/")[0]) if "/" in str(energy_val) else None
                if energy_num is not None:
                    if energy_num <= 2:
                        styles[idx.index("Energy")] = "background-color: #f8d7da; color: #721c24"
                    elif energy_num >= 4:
                        styles[idx.index("Energy")] = "background-color: #d4edda; color: #155724"

                if soreness_val == "High":
                    styles[idx.index("Soreness")] = "background-color: #f8d7da"
                elif soreness_val == "None":
                    styles[idx.index("Soreness")] = "background-color: #d4edda"

                if readiness_val == "Yes":
                    styles[idx.index("Readiness")] = "background-color: #d4edda"
                elif readiness_val == "No":
                    styles[idx.index("Readiness")] = "background-color: #f8d7da"

                return styles

            st.dataframe(
                roster_df.style.apply(color_row, axis=1),
                use_container_width=True,
                hide_index=True,
                height=min(50 + len(rows) * 38, 500),
            )

            st.markdown("---")
            st.markdown("### Athlete Cards")
            col_count = min(len(athletes), 3)
            cols = st.columns(max(col_count, 1))
            for i, (phone, athlete) in enumerate(athletes.items()):
                athlete_df = df_all[df_all["phone"] == phone].copy() if not df_all.empty else pd.DataFrame()
                aname = athlete.get("name", phone)

                if athlete_df.empty:
                    avg_e, last_ci, today_ready, streak = 0.0, "Never", "No data", 0
                else:
                    last_ci = athlete_df["date"].max().strftime("%b %d")
                    avg_e = athlete_df["energy"].mean()
                    today_df = athlete_df[athlete_df["date"] == today]
                    today_ready = today_df["readiness"].iloc[-1] if not today_df.empty else "Not yet"
                    streak = get_athlete_streak(athlete_df)

                ready_icon = {"Yes": "🟢", "No": "🔴", "Maybe": "🟡"}.get(str(today_ready), "⚪")
                with cols[i % col_count]:
                    st.markdown(f"""
                    <div class="athlete-card">
                        <h4 style="margin:0 0 8px 0;">{aname}</h4>
                        <p style="margin:2px 0; font-size:0.9rem;">⚡ Avg Energy: <b>{avg_e:.1f}/5</b></p>
                        <p style="margin:2px 0; font-size:0.9rem;">📅 Last: <b>{last_ci}</b></p>
                        <p style="margin:2px 0; font-size:0.9rem;">🔥 Streak: <b>{streak} days</b></p>
                        <p style="margin:2px 0; font-size:0.9rem;">{ready_icon} Today: <b>{today_ready}</b></p>
                    </div>
                    """, unsafe_allow_html=True)

    # ── Tab 2: Athlete Trends ─────────────────────────────────────────────────
    with tab2:
        if not athletes:
            st.info("No athletes linked yet.")
        else:
            athlete_options = {phone: u.get("name", phone) for phone, u in athletes.items()}
            selected_phone = st.selectbox(
                "Select Athlete",
                options=list(athlete_options.keys()),
                format_func=lambda p: athlete_options.get(p, p),
            )

            col1, col2 = st.columns(2)
            with col1:
                date_from = st.date_input("From", value=datetime.now() - timedelta(days=30))
            with col2:
                date_to = st.date_input("To", value=datetime.now())

            a_df = df_all[
                (df_all["phone"] == selected_phone) &
                (df_all["date"] >= pd.Timestamp(date_from)) &
                (df_all["date"] <= pd.Timestamp(date_to))
            ].copy() if not df_all.empty else pd.DataFrame()

            if a_df.empty:
                st.warning("No check-ins in this range.")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Check-ins", len(a_df))
                c2.metric("Avg Energy", f"{a_df['energy'].mean():.1f}/5")
                c3.metric("Avg Sleep", f"{a_df['sleep_hours'].mean():.1f}hrs")
                c4.metric("Ready %", f"{(a_df['readiness'] == 'Yes').mean() * 100:.0f}%")

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=a_df["date"], y=a_df["energy"],
                                         mode="lines+markers", name="Energy (1–5)",
                                         line=dict(color="#22c55e", width=2), marker=dict(size=7)))
                fig.add_trace(go.Scatter(x=a_df["date"], y=a_df["sleep_score"],
                                         mode="lines+markers", name="Sleep Quality (1–4)",
                                         line=dict(color="#128c7e", width=2, dash="dot"), marker=dict(size=7)))
                fig.add_trace(go.Scatter(x=a_df["date"], y=a_df["soreness_score"],
                                         mode="lines+markers", name="Recovery (4=Good)",
                                         line=dict(color="#e67e22", width=2, dash="dash"), marker=dict(size=7)))

                fig.add_hrect(y0=0, y1=2, fillcolor="rgba(220,53,69,0.05)", line_width=0,
                              annotation_text="Low zone", annotation_position="left")
                fig.add_hrect(y0=4, y1=5, fillcolor="rgba(37,211,102,0.05)", line_width=0,
                              annotation_text="High zone", annotation_position="left")

                fig.update_layout(
                    title=f"{athlete_options[selected_phone]} — Wellness Trends",
                    xaxis_title="Date", yaxis_title="Score",
                    hovermode="x unified", height=400,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="#16213e", paper_bgcolor="#16213e", font=dict(color='rgba(255,255,255,0.7)'),
                )
                st.plotly_chart(fig, use_container_width=True)

                soreness_hist = a_df["soreness"].value_counts().reset_index()
                soreness_hist.columns = ["Soreness", "Days"]
                order_s = ["None", "Mild", "Moderate", "High"]
                color_s = {"None": "#22c55e", "Mild": "#8bc34a", "Moderate": "#ffc107", "High": "#dc3545"}
                soreness_hist = soreness_hist.set_index("Soreness").reindex(order_s).dropna().reset_index()
                col_s, col_ai = st.columns([1, 1])
                with col_s:
                    fig_sor = px.bar(soreness_hist, x="Soreness", y="Days",
                                     color="Soreness", color_discrete_map=color_s,
                                     title="Soreness Breakdown", text="Days")
                    fig_sor.update_traces(textposition="outside")
                    fig_sor.update_layout(showlegend=False, height=300, plot_bgcolor="#16213e", paper_bgcolor="#16213e", font=dict(color='rgba(255,255,255,0.7)'))
                    st.plotly_chart(fig_sor, use_container_width=True)

                with col_ai:
                    st.markdown("### AI Recommendation")
                    suggestion = ai_suggestion(a_df)
                    if suggestion:
                        st.markdown(f"""
                        <div class="ai-box">
                            {suggestion.replace(chr(10), "<br>")}
                        </div>
                        """, unsafe_allow_html=True)

    # ── Tab 3: Group Analytics ────────────────────────────────────────────────
    with tab3:
        if not athletes or df_all.empty:
            st.info("No data yet.")
        else:
            all_phones = list(athletes.keys())
            team_df = df_all[df_all["phone"].isin(all_phones)].copy()

            if team_df.empty:
                st.info("No check-ins recorded for your athletes yet.")
            else:
                last_7 = team_df[team_df["date"] >= today - timedelta(days=7)]
                c1, c2, c3, c4 = st.columns(4)
                if not last_7.empty:
                    c1.metric("Team Check-ins (7d)", len(last_7))
                    c2.metric("Team Avg Energy", f"{last_7['energy'].mean():.1f}/5")
                    checked_today = len(team_df[team_df["date"] == today]["phone"].unique())
                    c3.metric("Checked In Today", f"{checked_today}/{len(athletes)}")
                    c4.metric("Team Ready %", f"{(last_7['readiness'] == 'Yes').mean() * 100:.0f}%")

                st.markdown("---")

                if not last_7.empty:
                    avg_by_name = last_7.groupby("name")["energy"].mean().reset_index()
                    avg_by_name.columns = ["Athlete", "Avg Energy"]
                    avg_by_name = avg_by_name.sort_values("Avg Energy")
                    fig_bar = px.bar(
                        avg_by_name, x="Avg Energy", y="Athlete", orientation="h",
                        color="Avg Energy",
                        color_continuous_scale=["#dc3545", "#ffc107", "#22c55e"],
                        range_color=[1, 5],
                        title="Team Energy — Last 7 Days",
                        text=avg_by_name["Avg Energy"].round(1),
                    )
                    fig_bar.update_traces(textposition="outside")
                    fig_bar.update_layout(height=max(250, 50 * len(avg_by_name)),
                                          coloraxis_showscale=False, yaxis_title="",
                                          plot_bgcolor="#16213e", paper_bgcolor="#16213e")
                    st.plotly_chart(fig_bar, use_container_width=True)

                col_pie, col_line = st.columns(2)

                with col_pie:
                    soreness_team = team_df["soreness"].value_counts().reset_index()
                    soreness_team.columns = ["Soreness", "Count"]
                    color_s = {"None": "#22c55e", "Mild": "#8bc34a", "Moderate": "#ffc107", "High": "#dc3545"}
                    fig_pie = px.pie(soreness_team, names="Soreness", values="Count",
                                     color="Soreness", color_discrete_map=color_s,
                                     title="Team Soreness Distribution")
                    fig_pie.update_layout(height=320, paper_bgcolor="#16213e", font=dict(color='rgba(255,255,255,0.7)'))
                    st.plotly_chart(fig_pie, use_container_width=True)

                with col_line:
                    weekly = (
                        team_df.set_index("date")
                        .resample("W")["energy"]
                        .mean()
                        .reset_index()
                    )
                    fig_wk = px.line(weekly, x="date", y="energy",
                                     title="Team Avg Energy — Weekly Trend",
                                     markers=True,
                                     labels={"energy": "Avg Energy", "date": "Week"})
                    fig_wk.update_traces(line_color="#22c55e", line_width=2, marker_size=7)
                    fig_wk.update_layout(height=320, yaxis_range=[1, 5],
                                         plot_bgcolor="#16213e", paper_bgcolor="#16213e")
                    st.plotly_chart(fig_wk, use_container_width=True)

    # ── Tab 4: Invite Athlete ─────────────────────────────────────────────────
    with tab4:
        import qrcode, io as _io
        from PIL import Image as _Image

        # ── Slot usage indicator ───────────────────────────────────────────
        _coach_plan = st.session_state.get("plan", "")
        # Trial coaches get 8 slots (same as starter) so they can evaluate with their real team
        _slot_limits = {"coach_starter": 8, "coach_team": 20, "coach_club": 60, "coach_pro": 8, "trial": 8}
        _slot_limit = _slot_limits.get(_coach_plan, 0)
        _slot_used  = len(athletes)
        if _slot_limit:
            _pct = min(100, int(_slot_used / _slot_limit * 100))
            _color = "#22c55e" if _pct < 75 else "#f59e0b" if _pct < 100 else "#ef4444"
            st.markdown(
                f"""<div style="background:#16213e;border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:16px;box-shadow:0 2px 12px rgba(0,0,0,0.3)">
  <div style="flex:1">
    <div style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Athlete Slots</div>
    <div style="background:rgba(255,255,255,0.1);border-radius:99px;height:8px;overflow:hidden">
      <div style="background:{_color};height:100%;width:{_pct}%;border-radius:99px;transition:width .3s"></div>
    </div>
    <div style="font-size:12px;color:rgba(255,255,255,0.45);margin-top:5px">{_slot_used} of {_slot_limit} slots used</div>
  </div>
  <div style="font-size:22px;font-weight:800;color:{_color}">{_slot_used}/{_slot_limit}</div>
</div>""",
                unsafe_allow_html=True,
            )
            if _slot_used >= _slot_limit:
                st.warning("⚠️ You've reached your athlete limit. Upgrade your plan to invite more athletes.")
        _replit_domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0] or os.environ.get("REPLIT_DEV_DOMAIN", "")
        _base_signup = f"https://{_replit_domain}/api/signup" if _replit_domain else "https://runnerwellnessapp.com/api/signup"

        st.markdown("Type your athletes' names below — one per line. Each gets a personalised invite link. When they open it they skip the plan picker and join your team free.")

        _remaining_slots = (_slot_limit - _slot_used) if _slot_limit else 999
        _placeholder_names = "Alex\nJordan\nMorgan\nSam\nTaylor"
        names_raw = st.text_area(
            "👥 Athlete names (one per line)",
            placeholder=_placeholder_names,
            height=160,
            help=f"You have {_remaining_slots} slot{'s' if _remaining_slots != 1 else ''} remaining on your plan.",
        )

        _names = [n.strip() for n in names_raw.splitlines() if n.strip()]

        if _names:
            if _slot_limit and len(_names) > _remaining_slots:
                st.warning(f"⚠️ You've entered {len(_names)} names but only have {_remaining_slots} slot{'s' if _remaining_slots != 1 else ''} available. Only the first {_remaining_slots} link{'s' if _remaining_slots != 1 else ''} will count toward your plan.")

            # Build link rows
            _rows = []
            for _n in _names:
                _url = f"{_base_signup}?name={_n.replace(' ', '+')}&coach={coach_phone}"
                _rows.append({"Athlete": _n, "Invite Link": _url})

            # Native dataframe with clickable links
            _links_df = pd.DataFrame(_rows)
            st.dataframe(
                _links_df,
                column_config={
                    "Athlete": st.column_config.TextColumn("Athlete", width="small"),
                    "Invite Link": st.column_config.LinkColumn("Invite Link", display_text="Open link ↗"),
                },
                use_container_width=True,
                hide_index=True,
                height=min(400, 36 + len(_rows) * 35),
            )

            # CSV download
            import csv as _csv
            _csv_buf = _io.StringIO()
            _writer = _csv.DictWriter(_csv_buf, fieldnames=["Athlete", "Invite Link"])
            _writer.writeheader()
            _writer.writerows(_rows)
            st.download_button(
                label="⬇️ Download all links as CSV",
                data=_csv_buf.getvalue(),
                file_name="athlete_invite_links.csv",
                mime="text/csv",
            )
            st.caption("Open the CSV in Excel or Google Sheets to copy-paste links into your email or messaging app.")

            # QR code — single athlete only (not practical for large squads)
            if len(_names) == 1:
                _url1 = _rows[0]["Invite Link"]
                _qr1 = qrcode.make(_url1)
                _qbuf1 = _io.BytesIO()
                _qr1.save(_qbuf1, format="PNG")
                _qbuf1.seek(0)
                _qimg = _qbuf1.getvalue()
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(_qimg, caption=f"Scan to join as {_names[0]}", width=200)
            elif len(_names) <= 12:
                with st.expander(f"📱 Show QR codes ({len(_names)} athletes)"):
                    _ncols = min(4, len(_names))
                    for _chunk_start in range(0, len(_rows), _ncols):
                        _chunk = _rows[_chunk_start:_chunk_start + _ncols]
                        _row_cols = st.columns(_ncols)
                        for _ci, _r in enumerate(_chunk):
                            _qr = qrcode.make(_r["Invite Link"])
                            _qb = _io.BytesIO()
                            _qr.save(_qb, format="PNG")
                            _qb.seek(0)
                            _row_cols[_ci].image(_qb.getvalue(), caption=_r["Athlete"], width=140)
        else:
            st.info("Enter at least one athlete name above to generate invite links.")

        st.markdown("---")
        st.markdown("### Current Team")
        if not athletes:
            st.info("No athletes linked yet.")
        else:
            for phone, athlete in athletes.items():
                aname = athlete.get("name", phone)
                a_df = df_all[df_all["phone"] == phone].copy() if not df_all.empty else pd.DataFrame()
                last = a_df["date"].max().strftime("%b %d") if not a_df.empty else "Never"
                st.markdown(f"🏃 **{aname}** ({phone}) — last check-in: {last}")

    # ── Tab 5: Export ─────────────────────────────────────────────────────────
    with tab5:
        if not athletes:
            st.info("No athletes linked yet.")
        else:
            all_phones = list(athletes.keys())
            team_df = df_all[df_all["phone"].isin(all_phones)].copy() if not df_all.empty else pd.DataFrame()

            col1, col2 = st.columns(2)
            with col1:
                date_from = st.date_input("From date", value=datetime.now() - timedelta(days=90))
            with col2:
                date_to = st.date_input("To date", value=datetime.now())

            athlete_filter = st.multiselect(
                "Filter athletes (leave blank for all)",
                options=all_phones,
                format_func=lambda p: athletes.get(p, {}).get("name", p),
            )
            phones_to_export = athlete_filter if athlete_filter else all_phones

            if team_df.empty:
                st.info("No check-ins recorded for your team yet.")
            else:
                export_df = team_df[
                    (team_df["phone"].isin(phones_to_export)) &
                    (team_df["date"] >= pd.Timestamp(date_from)) &
                    (team_df["date"] <= pd.Timestamp(date_to))
                ][["name", "date", "sleep", "feeling", "energy", "soreness", "readiness"]].copy()
                export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
                export_df = export_df.sort_values(["name", "date"], ascending=[True, False])
                export_df.columns = ["Athlete", "Date", "Sleep", "Feeling", "Energy", "Soreness", "Readiness"]

                st.markdown(f"**{len(export_df)} records** for {len(phones_to_export)} athlete(s)")
                st.dataframe(export_df, use_container_width=True, hide_index=True)

                csv_buf = io.StringIO()
                export_df.to_csv(csv_buf, index=False)
                st.download_button(
                    label="⬇️ Download Team CSV",
                    data=csv_buf.getvalue().encode("utf-8"),
                    file_name=f"team_checkins_{date_from}_{date_to}.csv",
                    mime="text/csv",
                    type="primary",
                )



def load_analytics():
    try:
        with open(ANALYTICS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    entries = []
    for d in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = os.path.join(BACKUP_DIR, d)
        if os.path.isdir(path) and len(d) == 10:
            files = os.listdir(path)
            size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
            size_str = f"{size/1024:.0f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
            entries.append({"date": d, "files": len(files), "size": size_str})
    return entries


def load_subscriptions() -> dict:
    """Load subscriptions.json — keyed by stripped phone number (digits only)."""
    try:
        with open(SUBSCRIPTIONS_FILE, "r") as f:
            data = json.load(f)
        return data.get("subscriptions", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def show_admin_dashboard(df_all, users):
    render_header("Admin", "admin", "admin")

    coaches = {p: u for p, u in users.items() if u.get("role") == "coach"}
    runners = {p: u for p, u in users.items() if u.get("role") == "runner"}
    subscriptions = load_subscriptions()
    now_ms = time.time() * 1000

    # Only count active, non-expired subscriptions with a non-free plan
    active_subs = {
        phone: sub for phone, sub in subscriptions.items()
        if sub.get("status") == "active"
        and sub.get("plan", "free") not in ("free", "")
        and (not sub.get("expiresAt") or sub["expiresAt"] > now_ms)
    }

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 All Trends", "📈 Analytics", "💳 Subscribers", "👥 Coach View", "📤 Export All"
    ])

    # ── Tab 1: Platform Overview ──────────────────────────────────────────────
    with tab1:
        today = pd.Timestamp(datetime.now().date())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Users", len(users))
        c2.metric("Coaches", len(coaches))
        c3.metric("Runners", len(runners))
        c4.metric("Paid Subscribers", len(active_subs))
        checked_today = len(df_all[df_all["date"] == today]["phone"].unique()) if not df_all.empty else 0
        c5.metric("Check-ins Today", checked_today)

        if not df_all.empty:
            weekly = df_all.set_index("date").resample("W")["energy"].mean().reset_index()
            fig = px.line(weekly, x="date", y="energy",
                          title="Platform Avg Energy — Weekly",
                          markers=True,
                          labels={"energy": "Avg Energy", "date": "Week"})
            fig.update_traces(line_color="#22c55e", line_width=2)
            fig.update_layout(height=350, yaxis_range=[1, 5],
                               plot_bgcolor="#16213e", paper_bgcolor="#16213e")
            st.plotly_chart(fig, use_container_width=True)

    # ── Tab 2: Analytics ──────────────────────────────────────────────────────
    with tab2:
        col_refresh, _ = st.columns([1, 5])
        with col_refresh:
            if st.button("🔄 Refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        analytics = load_analytics()
        checkins_stats = analytics.get("checkins", {})
        commands = analytics.get("commands", {})
        dau_raw = analytics.get("dailyActiveUsers", {})
        errors = analytics.get("errors", [])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Check-ins", checkins_stats.get("total", 0))
        c2.metric("Full Check-ins", checkins_stats.get("full", 0))
        c3.metric("Quick Check-ins", checkins_stats.get("quick", 0))
        c4.metric("Registrations", analytics.get("registrations", 0))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("First Contacts", analytics.get("firstContacts", 0))
        today_key = datetime.now().strftime("%Y-%m-%d")
        dau_today = len(dau_raw.get(today_key, []))
        c6.metric("Active Today", dau_today)
        c7.metric("Errors (last 100)", len(errors))
        last_7_keys = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        dau_7 = sum(len(dau_raw.get(k, [])) for k in last_7_keys)
        c8.metric("Active (7d)", dau_7)

        st.markdown("---")

        if commands:
            st.markdown("### Command Usage")
            cmd_df = pd.DataFrame(
                [{"Command": k, "Uses": v} for k, v in sorted(commands.items(), key=lambda x: -x[1])]
            )
            fig_cmd = px.bar(
                cmd_df, x="Uses", y="Command", orientation="h",
                color="Uses", color_continuous_scale=["#e8f5e9", "#22c55e"],
                title="Most Used Commands",
            )
            fig_cmd.update_layout(height=max(300, 40 * len(cmd_df)), coloraxis_showscale=False, yaxis_title="",
                                   plot_bgcolor="#16213e", paper_bgcolor="#16213e")
            st.plotly_chart(fig_cmd, use_container_width=True)

        if dau_raw:
            st.markdown("### Daily Active Users (last 30 days)")
            dau_list = []
            for i in range(30):
                day = (datetime.now() - timedelta(days=29 - i)).strftime("%Y-%m-%d")
                dau_list.append({"Date": day, "Active Users": len(dau_raw.get(day, []))})
            dau_df = pd.DataFrame(dau_list)
            fig_dau = px.bar(dau_df, x="Date", y="Active Users",
                             color="Active Users",
                             color_continuous_scale=["#e8f5e9", "#22c55e"],
                             title="Daily Active Users")
            fig_dau.update_layout(height=320, coloraxis_showscale=False,
                                   plot_bgcolor="#16213e", paper_bgcolor="#16213e")
            st.plotly_chart(fig_dau, use_container_width=True)

        st.markdown("---")
        st.markdown("### Backups")
        backups = load_backups()
        if not backups:
            st.info("No backups yet. Backups run daily at 2 AM and on startup.")
        else:
            backup_df = pd.DataFrame(backups)
            backup_df.columns = ["Date", "Files", "Size"]
            st.dataframe(backup_df, use_container_width=True, hide_index=True)
            st.caption(f"Last {len(backups)} backup(s) kept · auto-pruned after 14 days")

        if errors:
            st.markdown("---")
            with st.expander(f"⚠️ Recent Errors ({len(errors)})", expanded=False):
                err_df = pd.DataFrame([
                    {"Time": datetime.fromtimestamp(e["ts"] / 1000).strftime("%m-%d %H:%M"),
                     "Phone": e["phone"][-4:].rjust(10, "*"),
                     "Error": e["msg"][:100]}
                    for e in errors[:20]
                ])
                st.dataframe(err_df, use_container_width=True, hide_index=True)

    # ── Tab 3: Subscribers ────────────────────────────────────────────────────
    with tab3:
        col_rsub, _ = st.columns([1, 5])
        with col_rsub:
            if st.button("🔄 Refresh", key="refresh_subs", use_container_width=True):
                st.rerun()

        if not subscriptions:
            st.info("No subscriptions on record yet.")
        else:
            rows = []
            for phone, sub in subscriptions.items():
                exp_ms = sub.get("expiresAt")
                activated_ms = sub.get("activatedAt")
                is_active = (
                    sub.get("status") == "active"
                    and sub.get("plan", "free") not in ("free", "")
                    and (not exp_ms or exp_ms > now_ms)
                )
                # Match phone to a user name
                user_entry = users.get(phone, users.get("+" + phone, {}))
                name = user_entry.get("name", "—")
                rows.append({
                    "Status": "✅ Active" if is_active else "❌ Inactive/Expired",
                    "Name": name,
                    "Phone": f"***{phone[-4:]}",
                    "Plan": PLAN_LABELS.get(sub.get("plan", "free"), sub.get("plan", "—")),
                    "Activated": datetime.fromtimestamp(activated_ms / 1000).strftime("%Y-%m-%d") if activated_ms else "—",
                    "Expires": datetime.fromtimestamp(exp_ms / 1000).strftime("%Y-%m-%d") if exp_ms else "—",
                    "Stripe Customer": sub.get("stripeCustomerId", "—"),
                })

            sub_df = pd.DataFrame(rows)
            active_count = sum(1 for r in rows if r["Status"].startswith("✅"))
            st.markdown(f"**{active_count} active paid subscriber(s)** · {len(rows)} total records")
            st.dataframe(sub_df, use_container_width=True, hide_index=True)

            # Revenue estimate
            price_map = {"solo_pro": 4.99, "coach_starter": 39.99, "coach_pro": 39.99,
                         "coach_team": 79.99, "coach_club": 149.99}
            mrr = sum(
                price_map.get(sub.get("plan", ""), 0)
                for sub in subscriptions.values()
                if sub.get("status") == "active"
                and sub.get("plan", "free") not in ("free", "")
                and (not sub.get("expiresAt") or sub["expiresAt"] > now_ms)
            )
            if mrr > 0:
                st.metric("Estimated MRR", f"${mrr:,.2f}/mo")

    # ── Tab 4: Coach View ─────────────────────────────────────────────────────
    with tab4:
        if not coaches:
            st.info("No coaches registered.")
        else:
            for phone, coach in coaches.items():
                athletes = {p: u for p, u in users.items() if u.get("coachPhone") == phone}
                sub = subscriptions.get(phone, {})
                plan_label = PLAN_LABELS.get(sub.get("plan", "free"), sub.get("plan", "Free"))
                st.markdown(f"**👥 Coach {coach.get('name', phone)}** — {plan_label} — {len(athletes)} athletes")
                for ap, au in athletes.items():
                    st.markdown(f"  🏃 {au.get('name', ap)}")
                st.markdown("")

    # ── Tab 5: Export All ─────────────────────────────────────────────────────
    with tab5:
        if df_all.empty:
            st.info("No check-in data yet.")
        else:
            export_df = df_all[["name", "date", "phone", "sleep", "feeling",
                                 "energy", "soreness", "readiness"]].copy()
            export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
            export_df = export_df.sort_values(["name", "date"], ascending=[True, False])
            export_df.columns = ["Athlete", "Date", "Phone", "Sleep", "Feeling",
                                 "Energy", "Soreness", "Readiness"]
            st.markdown(f"**{len(export_df)} total records**")
            st.dataframe(export_df, use_container_width=True, hide_index=True)

            csv_buf = io.StringIO()
            export_df.to_csv(csv_buf, index=False)
            st.download_button(
                "⬇️ Download All CSV",
                data=csv_buf.getvalue().encode("utf-8"),
                file_name=f"all_checkins_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary",
            )



def show_legal_page():
    tab = st.session_state.get("_legal_tab", "privacy")

    if st.button("← Back", key="legal_back_btn"):
        st.session_state.pop("_legal_tab", None)
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if tab == "privacy":
        st.markdown("## 📄 Privacy Policy")
        st.markdown("*Last updated: April 2026*")
        st.markdown(
            """
**Runner Wellness** ("we", "us", "our") operates the Runner Wellness SMS coaching service
and this dashboard. This policy explains what data we collect, how we use it, and your rights.

---

### 1. Information Collection
We collect the following information solely to provide coaching insights and predictions:
- **Phone number** — your account identifier and SMS delivery address.
- **Name** — to personalise your experience.
- **Birth year** (optional) — collected after your first check-in to calculate age-graded race predictions.
- **Daily check-in responses** — Sleep quality, Mood/feeling, Energy, Soreness, and Readiness to train (5 questions), plus optional free-text notes.
- **Goal race** — target race distance and date, used for training predictions.
- **Workout logs** — run type (track, road, or easy), distance or event, and time.

We do **not** collect location data, payment card details, or any biometric identifiers.

---

### 2. Use of Data
Your data is used to generate your daily wellness responses and coach dashboards.
We do **not** use your data for unrelated marketing. Specifically, we use it to:
- Deliver your daily SMS check-in and AI-generated coaching tips.
- Track your wellness trends and streak over time.
- Show your data in this personal dashboard.
- Share relevant summary data with a coach you have explicitly linked to your account.
- Generate aggregate (anonymised) statistics to improve the service.

---

### 3. No Third-Party Sharing
**Important:** We will not share, sell, or rent your SMS opt-in data or personal information
to third parties or affiliates for marketing or promotional purposes.

| Who | What they can see |
|---|---|
| You | Everything in your dashboard |
| Your linked coach | Your check-in scores and trends |
| Our staff | Account info only, for support purposes |
| Third parties | **Nothing** — we do not sell or share your data |

---

### 4. Data Security
We use industry-standard encryption to protect your logs and performance data.
Your data is stored in an encrypted PostgreSQL database. Passwords are hashed using bcrypt.
SMS messages are transmitted via Telnyx's secure platform. We retain your data for as long as
your account is active.

---

### 5. Opt-Out
You can opt-out at any time by texting **STOP** to our SMS number. You may also:
- **Delete your account** — text **DELETEDATA** to our SMS number or contact support@runnerwellnessapp.com
  and we will delete your account and all associated data within 30 days.
- **Access your data** — request a copy at any time via support.
- **Correct your data** — contact support to fix inaccurate information.
- **Export your data** — request an export of your check-in history in CSV format.

If you are in the European Economic Area, you have additional rights under GDPR (Articles 15–22).
We process your data on the legal basis of consent (Article 6(1)(a)). You may withdraw consent
at any time by deleting your account.

---

### 6. Cookies & tracking
This web dashboard does not use third-party tracking cookies or analytics services.
Streamlit may set a session cookie strictly necessary for the app to function.

---

### 7. Age policy
Users must be **16 or older**, or have explicit permission from a parent or guardian.

- **High school teams:** coach approval is recommended before athletes sign up.
- **Parents:** we encourage you to review the app with your teen before they create an account.

We do not knowingly collect data from children under 13. If you believe a child under 13 has
created an account, please contact us and we will delete it promptly.

---

### 8. Changes to this policy
We will notify you via SMS if we make material changes to this policy.

---

### 9. Contact
**Email:** support@runnerwellnessapp.com  
**SMS:** Text HELP to our check-in number for support.
"""
        )

    else:
        st.markdown("## 📋 Terms of Service")
        st.markdown("*Last updated: April 2026*")
        st.markdown(
            """
By creating a Runner Wellness account or using this service, you agree to the following terms.

---

### 1. Not a medical service
Runner Wellness is a **motivational wellness tracking tool**, not a medical service.

- Nothing in this app constitutes medical advice, diagnosis, or treatment.
- AI-generated coaching tips are for informational and motivational purposes only.
- Always consult a qualified physician, physiotherapist, or certified coach before changing
  your training programme, especially if you have an injury or underlying health condition.
- **Do not ignore professional medical advice based on anything this app says.**

---

### 2. SMS Terms of Service
*Effective Date: April 16, 2026*

**2.1 Program Description:** By opting into Runner Wellness, you are agreeing to receive
daily SMS wellness prompts and performance logging reminders. These messages help you track
energy, sleep, and soreness to optimise your training.

**2.2 Message Frequency:** You will receive approximately 2–3 messages per day — one morning
prompt and subsequent AI-driven responses based on your input.

**2.3 Cost:** Message and data rates may apply for any messages sent to you from us and to
us from you. If you have any questions about your text plan or data plan, please contact
your wireless provider.

**2.4 Support:** For help, text **HELP** to +1-844-983-3557 or email support@runnerwellnessapp.com.

**2.5 Opt-Out:** You can cancel the SMS service at any time by texting **STOP** to
+1-844-983-3557. After sending STOP, we will confirm your unsubscription via SMS. After
this, you will no longer receive SMS messages from us.

**2.6 Disclaimer:** Carriers are not liable for delayed or undelivered messages.

**2.7 Privacy:** We respect your privacy. All data collected in this programme will be used
in accordance with our Privacy Policy. We do not share your mobile information with third
parties for marketing purposes.

---

### 3. Your responsibilities
- You must provide accurate information when creating your account.
- You are responsible for keeping your login credentials secure.
- **Age:** you must be 16 or older, or have a parent or guardian's permission to use this service.
  - *High school teams:* coach approval is recommended before athletes join.
  - *Parents:* please review the app with your teen before they sign up.
- You agree not to use the service for any unlawful purpose.

---

### 4. Account termination
We reserve the right to suspend or terminate accounts that violate these terms, abuse the SMS
system, or engage in fraudulent activity. You may delete your account at any time.

---

### 5. Limitation of liability
To the maximum extent permitted by law, Runner Wellness and its operators shall not be liable
for any injury, loss, or damage arising from reliance on information provided by this app.
Your use of this service is entirely at your own risk.

---

### 6. Intellectual property
The Runner Wellness name, logo, and app content are proprietary. You may not reproduce or
redistribute them without permission.

---

### 7. Governing law
These terms are governed by the laws of the jurisdiction in which the operator is based.
Any disputes shall be resolved through good-faith negotiation before pursuing legal action.

---

### 8. Changes to these terms
We may update these terms from time to time. Continued use of the service after notification
constitutes acceptance of the updated terms.

---

### 9. Contact
**Email:** support@runnerwellnessapp.com
"""
        )


def show_footer():
    st.markdown(
        """
<div style="margin-top:32px; padding:20px 0 12px;
            border-top:1px solid rgba(255,255,255,0.07);
            text-align:center; font-family:'DM Sans',sans-serif;">
  <p style="margin:0 0 6px; font-size:0.78rem; color:rgba(255,255,255,0.35);
            letter-spacing:0.02em;">
    Richland, WA 99352 &nbsp;·&nbsp; Daily check-ins for peak performance
  </p>
  <a href="/api/contact"
     onclick="window.top.location.href='/api/contact'; return false;"
     style="font-size:0.78rem; color:rgba(252,76,2,0.7); text-decoration:none;
            font-weight:500; letter-spacing:0.01em; cursor:pointer;">
    Contact
  </a>
</div>
""",
        unsafe_allow_html=True,
    )


def inject_tile_css():
    """Inject nav-tile and sign-out CSS directly via st.markdown — guaranteed every render."""
    st.markdown("""
<style>
/* ── Nav tiles base ──────────────────────────────────────────────────────── */
button.rw-nt {
  background: linear-gradient(160deg, #0d1828 0%, #070d1a 100%) !important;
  border: 1px solid rgba(255,255,255,0.08) !important;
  border-radius: 20px !important;
  color: #fff !important;
  min-height: 118px !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 10px !important;
  cursor: pointer !important;
  position: relative !important;
  padding: 20px 10px 16px !important;
  transition: all 0.22s cubic-bezier(0.34, 1.4, 0.64, 1) !important;
  -webkit-tap-highlight-color: transparent !important;
  user-select: none !important;
  box-shadow:
    0 2px 0 rgba(255,255,255,0.04) inset,
    0 6px 24px rgba(0,0,0,0.55) !important;
}
button.rw-nt:hover {
  background: linear-gradient(160deg, #111e30 0%, #0c1828 100%) !important;
  border-color: rgba(0,229,192,0.28) !important;
  transform: translateY(-3px) scale(1.02) !important;
  box-shadow:
    0 2px 0 rgba(255,255,255,0.05) inset,
    0 10px 36px rgba(0,0,0,0.65),
    0 0 28px rgba(0,229,192,0.1) !important;
}
button.rw-nt:active {
  transform: scale(0.93) translateY(1px) !important;
  opacity: 0.88 !important;
}
/* ── Active tile (DASHBOARD) ──────────────────────────────────────────────── */
button.rw-nt.rw-nt-active {
  background: linear-gradient(145deg, #FF5A00 0%, #cc3200 48%, #7a1a00 100%) !important;
  border-color: rgba(255,110,0,0.35) !important;
  box-shadow:
    0 0 0 1px rgba(255,90,0,0.3),
    0 8px 30px rgba(255,70,0,0.5),
    0 22px 64px rgba(255,50,0,0.22),
    0 2px 0 rgba(255,200,80,0.22) inset !important;
}
button.rw-nt.rw-nt-active:hover {
  transform: translateY(-3px) scale(1.02) !important;
  box-shadow:
    0 0 0 1px rgba(255,90,0,0.35),
    0 12px 40px rgba(255,70,0,0.6),
    0 28px 72px rgba(255,50,0,0.28) !important;
}
/* ── Coach Z tile (teal accent, notification presence) ────────────────────── */
button.rw-nt.rw-nt-cz {
  background: linear-gradient(160deg, #0e1d14 0%, #07120f 100%) !important;
  border-color: rgba(0,229,192,0.25) !important;
  box-shadow:
    inset 0 1px 0 rgba(0,229,192,0.08),
    0 6px 24px rgba(0,0,0,0.55),
    inset 0 0 40px rgba(0,229,192,0.04) !important;
}
button.rw-nt.rw-nt-cz:hover {
  border-color: rgba(0,229,192,0.5) !important;
  box-shadow:
    0 10px 36px rgba(0,0,0,0.65),
    0 0 36px rgba(0,229,192,0.18),
    inset 0 0 40px rgba(0,229,192,0.08) !important;
}
button.rw-nt.rw-nt-cz.rw-nt-active {
  background: linear-gradient(145deg, #FF5A00 0%, #cc3200 48%, #7a1a00 100%) !important;
  border-color: rgba(255,110,0,0.35) !important;
}

/* ── History tile (teal-accented calendar card) ───────────────────────────── */
button.rw-nt.rw-nt-hist {
  background: linear-gradient(160deg, #0b1824 0%, #070e18 100%) !important;
  border-color: rgba(56,189,248,0.2) !important;
  box-shadow:
    inset 0 1px 0 rgba(56,189,248,0.07),
    0 6px 24px rgba(0,0,0,0.55) !important;
}
button.rw-nt.rw-nt-hist:hover {
  border-color: rgba(56,189,248,0.45) !important;
  box-shadow:
    0 10px 36px rgba(0,0,0,0.65),
    0 0 32px rgba(56,189,248,0.12) !important;
}
button.rw-nt.rw-nt-hist.rw-nt-active {
  background: linear-gradient(145deg, #FF5A00 0%, #cc3200 48%, #7a1a00 100%) !important;
  border-color: rgba(255,110,0,0.35) !important;
}


/* ── Icon container (glass square) ───────────────────────────────────────── */
.rw-nt-ic {
  width: 58px;
  height: 58px;
  border-radius: 16px;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.11);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 2px 8px rgba(0,0,0,0.45);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
button.rw-nt.rw-nt-active .rw-nt-ic {
  background: rgba(255,255,255,0.18) !important;
  border-color: rgba(255,255,255,0.26) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.22), 0 2px 10px rgba(0,0,0,0.3) !important;
}
button.rw-nt.rw-nt-cz .rw-nt-ic {
  background: rgba(0,229,192,0.1) !important;
  border-color: rgba(0,229,192,0.26) !important;
  box-shadow: inset 0 1px 0 rgba(0,229,192,0.15), 0 2px 10px rgba(0,0,0,0.45) !important;
}
button.rw-nt.rw-nt-hist .rw-nt-ic {
  background: rgba(56,189,248,0.09) !important;
  border-color: rgba(56,189,248,0.22) !important;
  box-shadow: inset 0 1px 0 rgba(56,189,248,0.12), 0 2px 10px rgba(0,0,0,0.45) !important;
}

/* ── Emoji icon ───────────────────────────────────────────────────────────── */
span.rw-nt-icon {
  font-size: 30px;
  line-height: 1;
  display: block;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}

/* ── Calendar widget (History) ───────────────────────────────────────────── */
span.rw-nt-month {
  font-size: 8px;
  font-weight: 900;
  letter-spacing: 0.2em;
  color: rgba(56,189,248,0.75);
  text-transform: uppercase;
  line-height: 1.4;
}
span.rw-nt-day {
  font-size: 26px;
  font-weight: 900;
  color: #fff;
  line-height: 1.0;
}
button.rw-nt.rw-nt-hist.rw-nt-active span.rw-nt-month {
  color: rgba(255,255,255,0.7) !important;
}

/* ── Streak and teaser text ───────────────────────────────────────────────── */
.rw-nt-streak {
  font-size: 10px;
  font-weight: 700;
  color: rgba(56,189,248,0.8);
  letter-spacing: 0.04em;
  line-height: 1;
  font-family: "DM Sans", system-ui, sans-serif;
  white-space: nowrap;
}
button.rw-nt.rw-nt-hist.rw-nt-active .rw-nt-streak {
  color: rgba(255,255,255,0.85) !important;
}
.rw-nt-teaser {
  font-size: 9.5px;
  font-weight: 600;
  color: rgba(255,255,255,0.38);
  letter-spacing: 0.02em;
  line-height: 1;
  font-family: "DM Sans", system-ui, sans-serif;
  white-space: nowrap;
  font-style: italic;
}
button.rw-nt.rw-nt-cz .rw-nt-teaser {
  color: rgba(0,229,192,0.6) !important;
}
button.rw-nt.rw-nt-active .rw-nt-teaser {
  color: rgba(255,255,255,0.65) !important;
  font-style: normal !important;
}

/* ── Label ────────────────────────────────────────────────────────────────── */
.rw-nt-lbl {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.38);
  font-family: "DM Sans", system-ui, sans-serif;
  line-height: 1;
}
button.rw-nt.rw-nt-active .rw-nt-lbl  { color: rgba(255,255,255,0.92) !important; }
button.rw-nt.rw-nt-cz .rw-nt-lbl     { color: rgba(0,229,192,0.65) !important; }
button.rw-nt.rw-nt-hist .rw-nt-lbl   { color: rgba(56,189,248,0.55) !important; }
button.rw-nt.rw-nt-cz.rw-nt-active .rw-nt-lbl   { color: rgba(255,255,255,0.92) !important; }
button.rw-nt.rw-nt-hist.rw-nt-active .rw-nt-lbl { color: rgba(255,255,255,0.92) !important; }

/* ── Notification dot (Coach Z) — large, unmissable ───────────────────────── */
.rw-nt-pulse {
  position: absolute;
  top: 11px;
  right: 11px;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #ff6b3d, #ff2200);
  box-shadow:
    0 0 0 2.5px rgba(5,10,18,0.9),
    0 0 12px rgba(255,50,0,1),
    0 0 28px rgba(255,50,0,0.55);
  animation: rwczp 1.8s ease-in-out infinite;
}
@keyframes rwczp {
  0%,100% {
    transform: scale(1);
    box-shadow: 0 0 0 2.5px rgba(5,10,18,0.9), 0 0 12px rgba(255,50,0,0.95), 0 0 28px rgba(255,50,0,0.5);
  }
  50% {
    transform: scale(1.5);
    box-shadow: 0 0 0 2.5px rgba(5,10,18,0.9), 0 0 20px rgba(255,50,0,1), 0 0 44px rgba(255,50,0,0.7);
  }
}

/* ── Force nav rows horizontal on ALL screen sizes ────────────────────────── */
/* Streamlit collapses columns when viewport < ~640px; we override that here.  */
/* We target any stHorizontalBlock that contains a button.rw-nt child.         */
/* Since CSS can't do parent-of, we rely on JS tagging .rw-nav-row on the row. */
.rw-nav-row {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  gap: 8px !important;
  width: 100% !important;
}
.rw-nav-row > [data-testid="stColumn"],
.rw-nav-row > div[data-testid="stColumn"] {
  flex: 1 1 0 !important;
  min-width: 0 !important;
  width: 0 !important;
  max-width: none !important;
  padding-left: 3px !important;
  padding-right: 3px !important;
}
@media (max-width: 768px) {
  button.rw-nt {
    min-height: 90px !important;
    padding: 10px 3px 8px !important;
    gap: 5px !important;
    border-radius: 14px !important;
  }
  .rw-nt-ic {
    width: 40px !important;
    height: 40px !important;
    border-radius: 11px !important;
  }
  span.rw-nt-icon { font-size: 20px !important; }
  span.rw-nt-day  { font-size: 18px !important; }
  .rw-nt-streak   { font-size: 8px !important; white-space: normal !important; text-align: center !important; }
  .rw-nt-teaser   { display: none !important; }
  .rw-nt-lbl      { font-size: 8px !important; letter-spacing: 0.06em !important; }
}

/* ── Sign Out button ──────────────────────────────────────────────────────── */
button.rw-signout {
  background: transparent !important;
  border: 2px solid #00E5C0 !important;
  border-radius: 16px !important;
  color: #00E5C0 !important;
  height: 52px !important;
  width: 100% !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  cursor: pointer !important;
  transition: all 0.18s ease !important;
  font-family: "DM Sans", system-ui, sans-serif !important;
  box-shadow: none !important;
}
button.rw-signout:hover {
  background: rgba(0,229,192,0.1) !important;
  border-color: #00E5C0 !important;
  box-shadow: 0 0 24px rgba(0,229,192,0.18) !important;
  color: #00E5C0 !important;
}
button.rw-signout:active {
  background: rgba(0,229,192,0.18) !important;
  transform: scale(0.98) !important;
}
</style>
""", unsafe_allow_html=True)


def inject_fonts():
    """Inject DM Sans + DM Mono into the parent document head — most reliable font-loading method in Streamlit."""
    components.html("""
<script>
(function(){
  var doc = window.parent.document;
  if (doc.getElementById('rw-dm-fonts')) return;
  var link = doc.createElement('link');
  link.id   = 'rw-dm-fonts';
  link.rel  = 'stylesheet';
  link.href = 'https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap';
  doc.head.appendChild(link);
  /* Also force the font onto html/body so nothing overrides it */
  function applyFont() {
    var style = doc.getElementById('rw-dm-font-override');
    if (!style) {
      style = doc.createElement('style');
      style.id = 'rw-dm-font-override';
      doc.head.appendChild(style);
    }
    style.textContent =
      "html, body, * { font-family: 'DM Sans', -apple-system, sans-serif !important; }" +
      "[class*='metric'] [class*='Value'], [data-testid='stMetricValue']," +
      ".rw-hist-day { font-family: 'DM Mono', monospace !important; }";
  }
  /* Run immediately and after fonts load */
  applyFont();
  link.onload = applyFont;
  setTimeout(applyFont, 500);
  setTimeout(applyFont, 1500);
})();
</script>
""", height=0)


def main():
    inject_pwa()
    inject_tab_dock()
    inject_tile_css()
    inject_fonts()

    if st.session_state.get("_legal_tab"):
        show_legal_page()
        return

    # ── Restore session from URL token (survives refreshes & server restarts) ──
    if not st.session_state.get("logged_in"):
        url_token = st.query_params.get("t", "")
        if url_token:
            session = validate_session_token(url_token)
            if session:
                st.session_state.logged_in = True
                st.session_state.phone = session["phone"]
                st.session_state.username = session["username"]
                st.session_state.plan = session["plan"]
                st.session_state.role = session["role"]
                st.session_state.name = session["name"]
                st.session_state.session_token = url_token

    if not st.session_state.get("logged_in"):
        show_login_page()
        return

    role = st.session_state.get("role", "runner")
    phone = st.session_state.get("phone")
    name = st.session_state.get("name", "User")
    plan = st.session_state.get("plan", "free")

    df_all, users = load_data()

    if role == "admin":
        show_admin_dashboard(df_all, users)
    elif role == "coach":
        show_coach_dashboard(phone, name, plan, df_all, users)
    else:
        show_runner_dashboard(phone, name, plan, df_all, users)

    # ── Sign-out at the very bottom ───────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:24px;padding:16px 0 4px;'
        'border-top:1px solid rgba(0,229,192,0.08);"></div>',
        unsafe_allow_html=True,
    )
    if st.button("Sign Out", key="signout_btn", use_container_width=True):
        token = st.session_state.get("session_token", "")
        if token:
            delete_session_token(token)
        st.query_params.clear()
        for k in ["logged_in", "phone", "username", "plan", "role", "name", "session_token"]:
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown(
        """
<div style="margin-top:16px; text-align:center; font-family:'DM Sans',sans-serif; padding-bottom:24px;">
  <p style="margin:0 0 5px; font-size:0.7rem; color:rgba(255,255,255,0.22);
            letter-spacing:0.03em; line-height:1.6;">
    Richland, WA 99352 &nbsp;·&nbsp; Daily check-ins for peak performance
  </p>
  <a href="/api/contact"
     onclick="window.top.location.href='/api/contact'; return false;"
     style="font-size:0.7rem; color:rgba(0,229,192,0.55); text-decoration:none;
            font-weight:600; letter-spacing:0.04em; cursor:pointer;
            text-transform:uppercase;">
    Contact
  </a>
</div>
""",
        unsafe_allow_html=True,
    )


main()
