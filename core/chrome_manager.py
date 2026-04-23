import subprocess
import uuid
import os
import socket
import random
import win32gui
import win32process
import win32con
import time
from core.session_store import add_session, get_session, get_sessions, update_session
import requests

_basedir = os.path.dirname(os.path.abspath(__file__))
CHROME_PATH = os.path.abspath(os.path.join(_basedir, "..", "bin", "chrome.exe"))
PROFILE_BASE_DIR = os.path.abspath(os.path.join(_basedir, "..", "profiles"))
VPN_CONFIGS_DIR = os.path.abspath(os.path.join(_basedir, "..", "vpn_configs"))

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

def get_random_ip_for_host(hostname):
    try:
        _, _, ip_list = socket.gethostbyname_ex(hostname)
        if ip_list:
            return random.choice(ip_list)
    except Exception:
        pass
    return hostname

def get_ip_info(proxy=None, vpn_server=None, username=None, password=None):
    try:
        proxies = None
        if vpn_server and username and password:
            proxy_url = f"https://{username}:{password}@{vpn_server}:443"
            proxies = {"http": proxy_url, "https": proxy_url}
        elif proxy:
            proxy_url = proxy if "://" in proxy else f"http://{proxy}"
            proxies = {"http": proxy_url, "https": proxy_url}

        # Use ip-api.com (JSON, no auth required for low frequency)
        response = requests.get("http://ip-api.com/json/", proxies=proxies, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("query", "Unknown"), data.get("timezone", "Unknown")
    except Exception as e:
        print(f"Error getting IP info: {e}")
    return "Unknown", "Unknown"

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

def create_proxy_auth_extension(proxy_host, proxy_port, username, password, session_id, scheme="http"):
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
            "privacy",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": ["content.js"],
                "run_at": "document_start",
                "all_frames": true
            }
        ],
        "minimum_chrome_version":"22.0.0"
    }
    """

    import json
    safe_username = json.dumps(username)
    safe_password = json.dumps(password)

    background_js = f"""
    if (chrome.privacy && chrome.privacy.network && chrome.privacy.network.webRTCIPHandlingPolicy) {{
        chrome.privacy.network.webRTCIPHandlingPolicy.set({{
            value: "disable_non_proxied_udp"
        }});
    }}

    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: {safe_username},
                    password: {safe_password}
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ["blocking"]
    );
    """

    content_js = """
    var s = document.createElement('script');
    s.textContent = `
        Object.defineProperty(navigator, 'platform', { get: () => 'iPhone' });
        Object.defineProperty(navigator, 'vendor', { get: () => 'Apple Computer, Inc.' });
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });

        // Block HTML5 Geolocation to prevent real physical location leaks
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition = function(success, error) {
                if (error) {
                    error({ code: 1, message: "User denied Geolocation" });
                }
            };
            navigator.geolocation.watchPosition = function(success, error) {
                if (error) {
                    error({ code: 1, message: "User denied Geolocation" });
                }
                return 0;
            };
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

def create_profile(vpn_server=None, proxy=None):
    session_id = str(uuid.uuid4())[:8]
    profile_dir = os.path.join(PROFILE_BASE_DIR, session_id)
    os.makedirs(profile_dir, exist_ok=True)
    
    # Load Surfshark Credentials for IP check
    creds_path = os.path.join(VPN_CONFIGS_DIR, "credentials.txt")
    username, password = "", ""
    if os.path.exists(creds_path):
        with open(creds_path, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                username, password = lines[0].strip(), lines[1].strip()

    ip, tz = get_ip_info(proxy, vpn_server, username, password)
    
    add_session(session_id, "CLOSED", "https://m.facebook.com", profile_dir, None, ip, tz, proxy, vpn_server)
    return session_id

def open_chrome(session_id=None, url="https://www.ident.me", proxy=None, vpn_server=None):
    # NEW SESSION
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        profile_dir = os.path.join(PROFILE_BASE_DIR, session_id)
        os.makedirs(profile_dir, exist_ok=True)
    else:
        session = get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        profile_dir = session["profile_dir"]
        proxy = proxy or session.get("proxy")
        vpn_server = vpn_server or session.get("vpn_server")

    profile_dir = os.path.abspath(profile_dir)

    # Fetch Surfshark Credentials
    creds_path = os.path.join(VPN_CONFIGS_DIR, "credentials.txt")
    username, password = "", ""
    if os.path.exists(creds_path):
        with open(creds_path, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                username, password = lines[0].strip(), lines[1].strip()

    # --- MOBILE USER AGENT ---
    # Spoof OS perfectly as an iPhone 14 Pro Max running iOS 16.6
    iphone_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    )

    # Grid layout logic
    sessions = get_sessions()
    open_sessions = [s for s in sessions.values() if s.get("status") == "OPEN"]
    slot_index = len(open_sessions)

    cols_per_row = 5
    win_width = 390  # Old device width
    win_height = 700 # Old device height
    
    col = slot_index % cols_per_row
    row = slot_index // cols_per_row
    x_pos = 50 + (col * (win_width + 10))
    y_pos = 50 + (row * 50)
    # -----------------------------------------------------

    # Build the Chrome command
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
        "--extensions-install-verification=none",
        "--disable-extensions-verification",
        "--use-mobile-user-agent",
        "--touch-events=enabled",
        "--enable-viewport",
        "--hide-scrollbars"
    ]

    # ✅ Handle Extensions and Proxy enforcement
    extensions = []
    
    vpn_server_for_ip_check = vpn_server

    # 1. Proxy Auth (highest priority if vpn_server or proxy is provided)
    if vpn_server and username and password:
        resolved_ip = get_random_ip_for_host(vpn_server)
        # We DO NOT set vpn_server_for_ip_check = resolved_ip here because
        # python 'requests' will fail SSL validation if an IP address is used
        # in the HTTPS proxy URL instead of the domain name.
        
        # Use the original hostname for the extension so the SSL certificate matches!
        ext_path = create_proxy_auth_extension(vpn_server, 443, username, password, session_id, scheme="https")
        extensions.append(ext_path)
        # Force Chrome to connect to the randomly resolved IP instead of caching the load balancer
        cmd.append(f'--host-resolver-rules=MAP {vpn_server} {resolved_ip}')
        cmd.append(f"--proxy-server=https://{vpn_server}:443")
        cmd.append("--ignore-certificate-errors")
        cmd.append("--test-type")
    elif proxy and "@" in proxy:
        try:
            p_part = proxy.split("@")
            auth_part = p_part[0]
            scheme = "http"
            if auth_part.startswith("https://"):
                scheme = "https"
                auth_part = auth_part.replace("https://", "")
            else:
                auth_part = auth_part.replace("http://", "")
            host_part = p_part[1]
            u, p = auth_part.split(":")
            h, pt = host_part.split(":")
            ext_path = create_proxy_auth_extension(h, pt, u, p, session_id, scheme=scheme)
            extensions.append(ext_path)
            cmd.append(f"--proxy-server={scheme}://{h}:{pt}")
            cmd.append("--ignore-certificate-errors")
            cmd.append("--test-type")
        except: pass

    # 2. Check for OFFICIAL Surfshark extension (only if no proxy/vpn was forced)
    if not extensions:
        official_surf_path = os.path.normpath(os.path.join(_basedir, "..", "surfshark_ext", "unpacked"))
        if os.path.exists(os.path.join(official_surf_path, "manifest.json")):
            extensions.append(official_surf_path)
            print(f"DEBUG: Found official extension at: {official_surf_path}")

    if extensions:
        ext_string = ",".join(extensions)
        cmd.append(f"--load-extension={ext_string}")
        cmd.append(f"--disable-extensions-except={ext_string}")

    # Open target URL and Extensions page
    cmd.append(url)
    cmd.append("chrome://extensions/")

    print(f"DEBUG: Running command: {' '.join(cmd)}")
    
    # Launch Chrome INSTANTLY
    proc = subprocess.Popen(cmd)

    # Save basic info first
    if not get_session(session_id):
        add_session(session_id, "OPEN", url, profile_dir, proc.pid, "Detecting...", "Detecting...", proxy, vpn_server)
    else:
        update_session(session_id, {
            "status": "OPEN",
            "pid": proc.pid,
            "proxy": proxy,
            "vpn_server": vpn_server
        })

    # Fetch IP info in background
    def update_ip_async():
        new_ip, new_tz = get_ip_info(proxy, vpn_server_for_ip_check, username, password)
        update_session(session_id, {"ip": new_ip, "timezone": new_tz})

    import threading
    threading.Thread(target=update_ip_async, daemon=True).start()

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

def delete_profile(session_id):
    session = get_session(session_id)
    if not session:
        return False, "Session not found"

    if session.get("status") == "OPEN":
        return False, "Cannot delete an open session. Close it first."

    profile_dir = session.get("profile_dir")
    
    # 1. Remove from session store
    from core.session_store import remove_session
    remove_session(session_id)

    # 2. Delete the physical directory
    import shutil
    if profile_dir and os.path.exists(profile_dir):
        try:
            shutil.rmtree(profile_dir)
            return True, "Profile deleted successfully"
        except Exception as e:
            return False, f"Error deleting directory: {str(e)}"
    
    return True, "Session removed, but directory was not found"
