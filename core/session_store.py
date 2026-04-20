import json
import os

import json
import os

# Get the directory where this script is located
_basedir = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_basedir, "..", "data", "sessions.json")

def load_sessions():
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return {}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_sessions(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_session(session_id, status, url, profile_dir, pid, ip="Unknown", timezone="Unknown", proxy=None, vpn_server=None):
    data = load_sessions()
    data[session_id] = {
        "status": status,
        "url": url,
        "profile_dir": profile_dir,
        "pid": pid,
        "ip": ip,
        "timezone": timezone,
        "proxy": proxy,
        "vpn_server": vpn_server
    }
    save_sessions(data)


def get_sessions():
    return load_sessions()


def get_session(session_id):
    data = load_sessions()
    return data.get(session_id)


def update_session(session_id, new_data):
    data = load_sessions()
    if session_id in data:
        data[session_id].update(new_data)
        save_sessions(data)


def remove_session(session_id):
    data = load_sessions()
    if session_id in data:
        del data[session_id]
        save_sessions(data)
