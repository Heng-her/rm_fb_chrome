import subprocess
import uuid
import os
import socket
import random
import win32gui
import win32process
import win32con
import time
import threading
import json
import shutil
from core.session_store import add_session, get_session, get_sessions, update_session
import requests

_basedir = os.path.dirname(os.path.abspath(__file__))
CHROME_PATH = os.path.abspath(os.path.join(_basedir, "..", "bin", "chrome.exe"))
PROFILE_BASE_DIR = os.path.abspath(os.path.join(_basedir, "..", "profiles"))
VPN_CONFIGS_DIR = os.path.abspath(os.path.join(_basedir, "..", "vpn_configs"))
ACCOUNTS_PATH = os.path.abspath(os.path.join(_basedir, "..", "accounts.json"))

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def is_pid_alive(pid):
    if not pid:
        return False
    try:
        cmd = f'tasklist /FI "PID eq {pid}" /NH'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        return str(pid) in output
    except Exception:
        return False


def get_random_ip_for_host(hostname):
    try:
        _, _, ip_list = socket.gethostbyname_ex(hostname)
        if ip_list:
            return random.choice(ip_list)
    except Exception:
        pass
    return hostname


def load_surfshark_credentials():
    creds_path = os.path.join(VPN_CONFIGS_DIR, "credentials.txt")
    if os.path.exists(creds_path):
        with open(creds_path, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
    return "", ""


def get_ip_info(proxy=None, vpn_server=None, username=None, password=None):
    try:
        proxies = None
        if vpn_server and username and password:
            proxy_url = f"https://{username}:{password}@{vpn_server}:443"
            proxies = {"http": proxy_url, "https": proxy_url}
        elif proxy:
            proxy_url = proxy if "://" in proxy else f"http://{proxy}"
            proxies = {"http": proxy_url, "https": proxy_url}

        response = requests.get("http://ip-api.com/json/", proxies=proxies, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("query", "Unknown"), data.get("timezone", "Unknown")
    except Exception as e:
        print(f"[get_ip_info] Error: {e}")
    return "Unknown", "Unknown"


def get_vpn_locations():
    locations = []
    if os.path.exists(VPN_CONFIGS_DIR):
        for f in os.listdir(VPN_CONFIGS_DIR):
            if f.endswith(".ovpn"):
                name = f.split(".prod")[0]
                server = f.replace("_tcp.ovpn", "").replace("_udp.ovpn", "")
                locations.append({"name": name, "server": server})
    return sorted(locations, key=lambda x: x["name"])


# ─────────────────────────────────────────────
# ACCOUNT STORE  (accounts.json)
# ─────────────────────────────────────────────

def load_accounts():
    if os.path.exists(ACCOUNTS_PATH):
        with open(ACCOUNTS_PATH, "r") as f:
            return json.load(f)
    return {}


def save_accounts(data):
    with open(ACCOUNTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def set_account_for_session(session_id, site_username, site_password, login_url="https://m.facebook.com"):
    accounts = load_accounts()
    accounts[session_id] = {
        "username": site_username,
        "password": site_password,
        "login_url": login_url
    }
    save_accounts(accounts)


def get_account_for_session(session_id):
    accounts = load_accounts()
    return accounts.get(session_id)


# ─────────────────────────────────────────────
# PROXY AUTH EXTENSION
# ─────────────────────────────────────────────

def create_proxy_auth_extension(proxy_host, proxy_port, username, password, session_id, scheme="http"):
    ext_path = os.path.join(PROFILE_BASE_DIR, session_id, "proxy_auth_ext")
    os.makedirs(ext_path, exist_ok=True)

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy Auth",
        "permissions": [
            "proxy", "tabs", "unlimitedStorage", "storage", "privacy",
            "<all_urls>", "webRequest", "webRequestBlocking"
        ],
        "background": { "scripts": ["background.js"] },
        "content_scripts": [{
            "matches": ["<all_urls>"],
            "js": ["content.js"],
            "run_at": "document_start",
            "all_frames": true
        }],
        "minimum_chrome_version": "22.0.0"
    }
    """

    safe_username = json.dumps(username)
    safe_password = json.dumps(password)

    background_js = f"""
    if (chrome.privacy?.network?.webRTCIPHandlingPolicy) {{
        chrome.privacy.network.webRTCIPHandlingPolicy.set({{ value: "disable_non_proxied_udp" }});
    }}
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{ authCredentials: {{ username: {safe_username}, password: {safe_password} }} }};
        }},
        {{ urls: ["<all_urls>"] }},
        ["blocking"]
    );
    """

    content_js = """
    var s = document.createElement('script');
    s.textContent = `
        Object.defineProperty(navigator, 'platform',       { get: () => 'iPhone' });
        Object.defineProperty(navigator, 'vendor',         { get: () => 'Apple Computer, Inc.' });
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition = (ok, err) => err && err({ code:1, message:'User denied Geolocation' });
            navigator.geolocation.watchPosition      = (ok, err) => { err && err({ code:1, message:'User denied Geolocation' }); return 0; };
        }
    `;
    (document.head || document.documentElement).appendChild(s);
    s.remove();
    """

    with open(os.path.join(ext_path, "manifest.json"), "w") as f:
        f.write(manifest_json)
    with open(os.path.join(ext_path, "background.js"), "w") as f:
        f.write(background_js)
    with open(os.path.join(ext_path, "content.js"), "w") as f:
        f.write(content_js)

    return ext_path


# ─────────────────────────────────────────────
# AUTO LOGIN  (Playwright)
# ─────────────────────────────────────────────

# Selector maps per domain — extend as needed
LOGIN_SELECTORS = {
    "facebook.com": {
        "username_field": 'input[name="email"]',
        "password_field": 'input[name="pass"]',
        "submit_button":  'button[name="login"]',
        "success_check":  '[aria-label="Home"]',   # element visible after login
    },
    "instagram.com": {
        "username_field": 'input[name="username"]',
        "password_field": 'input[name="password"]',
        "submit_button":  'button[type="submit"]',
        "success_check":  'svg[aria-label="Home"]',
    },
    # Add more sites here
}

def _get_selectors(login_url):
    for domain, sel in LOGIN_SELECTORS.items():
        if domain in login_url:
            return sel
    return None


def auto_login(session_id, login_url=None, site_username=None, site_password=None):
    """
    Perform auto-login for a session using Playwright.
    Credentials are loaded from accounts.json if not passed directly.
    Returns (success: bool, message: str).
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright && playwright install chromium"

    # Load credentials
    if not (site_username and site_password):
        account = get_account_for_session(session_id)
        if not account:
            return False, f"No credentials found for session {session_id}. Call set_account_for_session() first."
        site_username = account["username"]
        site_password = account["password"]
        login_url = login_url or account.get("login_url", "https://m.facebook.com")

    selectors = _get_selectors(login_url)
    if not selectors:
        return False, f"No login selectors configured for URL: {login_url}"

    session = get_session(session_id)
    if not session:
        return False, "Session not found"

    profile_dir = os.path.abspath(session["profile_dir"])
    proxy       = session.get("proxy")
    vpn_server  = session.get("vpn_server")
    username_vpn, password_vpn = load_surfshark_credentials()

    # Build Playwright proxy config
    pw_proxy = None
    if vpn_server and username_vpn:
        pw_proxy = {
            "server":   f"https://{vpn_server}:443",
            "username": username_vpn,
            "password": password_vpn,
        }
    elif proxy:
        proxy_url = proxy if "://" in proxy else f"http://{proxy}"
        pw_proxy = {"server": proxy_url}

    iphone_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    )

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir   = profile_dir,
                executable_path = CHROME_PATH,
                headless        = False,
                proxy           = pw_proxy,
                user_agent      = iphone_ua,
                viewport        = {"width": 390, "height": 700},
                ignore_https_errors = True,
                args            = [
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-sync",
                    "--touch-events=enabled",
                ]
            )

            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)

            # Fill username
            page.wait_for_selector(selectors["username_field"], timeout=15_000)
            page.fill(selectors["username_field"], site_username)

            # Fill password
            page.wait_for_selector(selectors["password_field"], timeout=10_000)
            page.fill(selectors["password_field"], site_password)

            # Small human-like delay
            time.sleep(random.uniform(0.5, 1.2))

            # Click login
            page.click(selectors["submit_button"])

            # Wait for success indicator
            try:
                page.wait_for_selector(selectors["success_check"], timeout=20_000)
                update_session(session_id, {"login_status": "LOGGED_IN"})

                # Keep browser open — detach from Playwright context
                context.close()
                return True, f"Login successful for {site_username}"

            except PWTimeout:
                context.close()
                return False, "Login may have failed — success element not found (wrong password / 2FA / captcha?)"

    except Exception as e:
        return False, f"Playwright error: {e}"


# ─────────────────────────────────────────────
# PROFILE MANAGEMENT
# ─────────────────────────────────────────────

def create_profile(vpn_server=None, proxy=None, site_username=None, site_password=None, login_url="https://m.facebook.com"):
    session_id  = str(uuid.uuid4())[:8]
    profile_dir = os.path.join(PROFILE_BASE_DIR, session_id)
    os.makedirs(profile_dir, exist_ok=True)

    username, password = load_surfshark_credentials()
    ip, tz = get_ip_info(proxy, vpn_server, username, password)

    add_session(session_id, "CLOSED", login_url, profile_dir, None, ip, tz, proxy, vpn_server)

    # Save site credentials if provided
    if site_username and site_password:
        set_account_for_session(session_id, site_username, site_password, login_url)

    return session_id


# ─────────────────────────────────────────────
# CHROME LAUNCH
# ─────────────────────────────────────────────

def open_chrome(session_id=None, url="https://m.facebook.com", proxy=None, vpn_server=None, auto_login_after=False):
    if not session_id:
        session_id  = str(uuid.uuid4())[:8]
        profile_dir = os.path.join(PROFILE_BASE_DIR, session_id)
        os.makedirs(profile_dir, exist_ok=True)
    else:
        session = get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        profile_dir = session["profile_dir"]
        proxy      = proxy      or session.get("proxy")
        vpn_server = vpn_server or session.get("vpn_server")
        url        = url        or session.get("url", "https://m.facebook.com")

    profile_dir  = os.path.abspath(profile_dir)
    username_vpn, password_vpn = load_surfshark_credentials()

    iphone_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    )

    # Grid layout
    sessions     = get_sessions()
    open_sessions = [s for s in sessions.values() if s.get("status") == "OPEN"]
    slot_index   = len(open_sessions)
    cols_per_row = 5
    win_width, win_height = 390, 700
    col   = slot_index % cols_per_row
    row   = slot_index // cols_per_row
    x_pos = 50 + col * (win_width + 10)
    y_pos = 50 + row * 50

    cmd = [
        CHROME_PATH,
        f"--user-data-dir={profile_dir}",
        "--new-window",
        f"--user-agent={iphone_ua}",
        f"--window-size={win_width},{win_height}",
        f"--window-position={x_pos},{y_pos}",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--extensions-install-verification=none",
        "--disable-extensions-verification",
        "--use-mobile-user-agent",
        "--touch-events=enabled",
        "--enable-viewport",
        "--hide-scrollbars",
    ]

    extensions          = []
    vpn_server_for_ip   = vpn_server

    if vpn_server and username_vpn and password_vpn:
        resolved_ip = get_random_ip_for_host(vpn_server)
        ext_path    = create_proxy_auth_extension(vpn_server, 443, username_vpn, password_vpn, session_id, scheme="https")
        extensions.append(ext_path)
        cmd += [
            f"--host-resolver-rules=MAP {vpn_server} {resolved_ip}",
            f"--proxy-server=https://{vpn_server}:443",
            "--ignore-certificate-errors",
            "--test-type",
        ]
    elif proxy and "@" in proxy:
        try:
            p_part    = proxy.split("@")
            auth_part = p_part[0]
            scheme    = "https" if auth_part.startswith("https://") else "http"
            auth_part = auth_part.replace("https://", "").replace("http://", "")
            host_part = p_part[1]
            u, p_pw   = auth_part.split(":", 1)       # maxsplit=1 handles passwords with ':'
            h, pt     = host_part.rsplit(":", 1)
            ext_path  = create_proxy_auth_extension(h, int(pt), u, p_pw, session_id, scheme=scheme)
            extensions.append(ext_path)
            cmd += [
                f"--proxy-server={scheme}://{h}:{pt}",
                "--ignore-certificate-errors",
                "--test-type",
            ]
        except Exception as e:
            print(f"[open_chrome] Proxy parse error: {e}")

    if not extensions:
        official_surf_path = os.path.normpath(os.path.join(_basedir, "..", "surfshark_ext", "unpacked"))
        if os.path.exists(os.path.join(official_surf_path, "manifest.json")):
            extensions.append(official_surf_path)

    if extensions:
        ext_string = ",".join(extensions)
        cmd += [f"--load-extension={ext_string}", f"--disable-extensions-except={ext_string}"]

    cmd += [url, "chrome://extensions/"]

    print(f"[open_chrome] Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)

    if not get_session(session_id):
        add_session(session_id, "OPEN", url, profile_dir, proc.pid, "Detecting...", "Detecting...", proxy, vpn_server)
    else:
        update_session(session_id, {"status": "OPEN", "pid": proc.pid, "proxy": proxy, "vpn_server": vpn_server})

    # Background: IP detection
    def update_ip_async():
        new_ip, new_tz = get_ip_info(proxy, vpn_server_for_ip, username_vpn, password_vpn)
        update_session(session_id, {"ip": new_ip, "timezone": new_tz})

    threading.Thread(target=update_ip_async, daemon=True).start()

    # Background: auto login
    if auto_login_after:
        def do_login():
            time.sleep(4)   # wait for Chrome to fully load
            ok, msg = auto_login(session_id, login_url=url)
            print(f"[auto_login] session={session_id} | {msg}")
            update_session(session_id, {"login_status": "LOGGED_IN" if ok else "LOGIN_FAILED"})

        threading.Thread(target=do_login, daemon=True).start()

    return session_id


# ─────────────────────────────────────────────
# CLOSE / DELETE
# ─────────────────────────────────────────────

def close_chrome(session_id):
    session = get_session(session_id)
    if not session:
        return False, "Session not found"

    pid = session.get("pid")
    if not pid:
        return False, "PID not found"

    closed = False

    def enum_windows(hwnd, _):
        nonlocal closed
        try:
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed = True
        except Exception:
            pass

    win32gui.EnumWindows(enum_windows, None)

    if not closed:
        update_session(session_id, {"status": "CLOSED"})
        return True, "Chrome already closed"

    time.sleep(1.5)
    update_session(session_id, {"status": "CLOSED"})
    return True, "Chrome closed gracefully"


def delete_profile(session_id):
    session = get_session(session_id)
    if not session:
        return False, "Session not found"

    if session.get("status") == "OPEN":
        return False, "Cannot delete an open session. Close it first."

    profile_dir = session.get("profile_dir")

    from core.session_store import remove_session
    remove_session(session_id)

    # Also remove from accounts.json
    accounts = load_accounts()
    if session_id in accounts:
        del accounts[session_id]
        save_accounts(accounts)

    if profile_dir and os.path.exists(profile_dir):
        try:
            shutil.rmtree(profile_dir)
            return True, "Profile deleted successfully"
        except Exception as e:
            return False, f"Error deleting directory: {e}"

    return True, "Session removed (directory not found)"