import subprocess
import uuid
import os
# import signal
import win32gui
import win32process
import win32con
import time
from core.session_store import add_session, get_session, get_sessions, update_session

_basedir = os.path.dirname(os.path.abspath(__file__))
CHROME_PATH = os.path.abspath(os.path.join(_basedir, "..", "bin", "chrome.exe"))
PROFILE_BASE_DIR = os.path.abspath(os.path.join(_basedir, "..", "profiles"))

def is_pid_alive(pid):
    if not pid:
        return False
    try:
        # Check if process is running using Windows tasklist
        cmd = f'tasklist /FI "PID eq {pid}" /NH'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        return str(pid) in output
    except Exception:
        return False
import requests

def get_ip_info():
    try:
        # Use ip-api.com (JSON, no auth required for low frequency)
        response = requests.get("http://ip-api.com/json/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("query", "Unknown"), data.get("timezone", "Unknown")
    except Exception:
        pass
    return "Unknown", "Unknown"
# https://www.ident.me/
# https://m.facebook.com

import random

VPN_CONFIGS_DIR = os.path.abspath(os.path.join(_basedir, "..", "vpn_configs"))

def get_vpn_locations():
    locations = []
    if os.path.exists(VPN_CONFIGS_DIR):
        for f in os.listdir(VPN_CONFIGS_DIR):
            if f.endswith(".ovpn"):
                # Extract clean name like 'us-chi'
                name = f.split(".prod")[0]
                server = f.replace("_tcp.ovpn", "").replace("_udp.ovpn", "")
                locations.append({"name": name, "server": server})
    return sorted(locations, key=lambda x: x["name"])

def create_proxy_auth_extension(proxy_host, proxy_port, username, password, session_id):
    """Creates a temporary extension to handle proxy authentication."""
    ext_path = os.path.join(PROFILE_BASE_DIR, session_id, "proxy_auth_ext")
    os.makedirs(ext_path, exist_ok=True)

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
            }},
            bypassList: ["localhost"]
        }}
    }};

    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: "{username}",
                    password: "{password}"
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ["blocking"]
    );
    """

    with open(os.path.join(ext_path, "manifest.json"), "w") as f:
        f.write(manifest_json)
    with open(os.path.join(ext_path, "background.js"), "w") as f:
        f.write(background_js)

    return ext_path

def open_chrome(session_id=None, url="https://www.ident.me", proxy=None, vpn_server=None):
    # NEW SESSION
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        profile_dir = os.path.join(PROFILE_BASE_DIR, session_id)
        os.makedirs(profile_dir, exist_ok=True)
        # Fetch IP info (this will be the backend IP unless you route the request through the same proxy)
        ip, tz = get_ip_info()
    else:
        session = get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        profile_dir = session["profile_dir"]
        ip = session.get("ip", "Unknown")
        tz = session.get("timezone", "Unknown")
        proxy = proxy or session.get("proxy")
        vpn_server = vpn_server or session.get("vpn_server")

    profile_dir = os.path.abspath(profile_dir)

    # Load Surfshark Credentials
    creds_path = os.path.join(VPN_CONFIGS_DIR, "credentials.txt")
    username, password = "", ""
    if os.path.exists(creds_path):
        with open(creds_path, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                username, password = lines[0].strip(), lines[1].strip()

    iphone_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/15.0 Mobile/15E148 Safari/604.1"
    )

    # Safer grid layout logic
    sessions = get_sessions()
    open_sessions = [s for s in sessions.values() if s.get("status") == "OPEN"]
    slot_index = len(open_sessions)

    cols_per_row = 4 # Reduced to 4 for safety
    win_width = 390
    win_height = 700
    
    col = slot_index % cols_per_row
    row = slot_index // cols_per_row
    
    # Use a small starting offset (e.g., 50, 50) to avoid the very edge
    x_pos = 50 + (col * (win_width + 10))
    y_pos = 50 + (row * 50) # Stack rows slightly rather than full height to keep visible

    cmd = [
        CHROME_PATH,
        f"--user-data-dir={profile_dir}",
        "--new-window",
        f"--user-agent={iphone_user_agent}",
        f"--window-size={win_width},{win_height}",
        f"--window-position={x_pos},{y_pos}",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-blink-features=AutomationControlled",
        "--excludeSwitches=enable-automation",
        url
    ]

    # ✅ Handle VPN via HTTP Proxy (Surfshark port 1232) + Auth Extension
    # Note: Surfshark SOCKS5 uses 1080, but HTTP 1232 is often more stable in Chrome
    if vpn_server and username and password:
        ext_path = create_proxy_auth_extension(vpn_server, 1232, username, password, session_id)
        cmd.append(f"--load-extension={ext_path}")
    elif proxy:
        cmd.append(f"--proxy-server={proxy}")

    proc = subprocess.Popen(cmd)

    if not get_session(session_id):
        add_session(session_id, "OPEN", url, profile_dir, proc.pid, ip, tz, proxy, vpn_server)
    else:
        update_session(session_id, {
            "status": "OPEN",
            "pid": proc.pid,
            "proxy": proxy,
            "vpn_server": vpn_server
        })

    return session_id


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
                # Send WM_CLOSE (same as clicking X / Ctrl+W)
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed = True
        except Exception:
            pass

    win32gui.EnumWindows(enum_windows, None)

    if not closed:
        update_session(session_id, {"status": "CLOSED"})
        return True, "Chrome already closed"

    # Give Chrome time to shut down cleanly
    time.sleep(1.5)

    update_session(session_id, {"status": "CLOSED"})
    return True, "Chrome closed gracefully"
