import subprocess
import uuid
import os
# import signal
import win32gui
import win32process
import win32con
import time
from core.session_store import add_session, get_session, update_session

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

def open_chrome(session_id=None, url="https://m.facebook.com"):
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

    profile_dir = os.path.abspath(profile_dir)

    iphone_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/15.0 Mobile/15E148 Safari/604.1"
    )

    proc = subprocess.Popen([
        CHROME_PATH,
        f"--user-data-dir={profile_dir}",
        "--new-window",

        # ✅ iPhone emulation
        f"--user-agent={iphone_user_agent}",
        "--window-size=390,700",
        "--force-device-scale-factor=1",

        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        url
    ])

    if not get_session(session_id):
        add_session(session_id, "OPEN", url, profile_dir, proc.pid)
    else:
        update_session(session_id, {
            "status": "OPEN",
            "pid": proc.pid
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
