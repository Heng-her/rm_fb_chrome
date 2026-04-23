from flask import Flask, jsonify, render_template, request
import threading
import webview
import os

from core.chrome_manager import open_chrome, close_chrome, is_pid_alive, get_vpn_locations, create_profile, delete_profile
from core.session_store import get_sessions, update_session

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/vpn_locations")
def vpn_locations():
    return jsonify(get_vpn_locations())

@app.route("/credentials", methods=["GET", "POST"])
def credentials_route():
    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vpn_configs", "credentials.txt")
    if request.method == "POST":
        data = request.json or {}
        username = data.get("username", "")
        password = data.get("password", "")
        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
        with open(creds_path, "w") as f:
            f.write(f"{username}\n{password}\n")
        return jsonify({"status": "success"})
    else:
        username, password = "", ""
        if os.path.exists(creds_path):
            with open(creds_path, "r") as f:
                lines = f.read().splitlines()
                if len(lines) >= 2:
                    username, password = lines[0].strip(), lines[1].strip()
        return jsonify({"username": username, "password": password})

@app.route("/create_profile", methods=["POST"])
def create_profile_route():
    data = request.json or {}
    proxy = data.get("proxy")
    vpn_server = data.get("vpn_server")
    try:
        session_id = create_profile(vpn_server=vpn_server, proxy=proxy)
        return jsonify({"session_id": session_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/open_chrome", methods=["POST"])
def open_chrome_route():
    data = request.json or {}
    session_id = data.get("session_id")
    proxy = data.get("proxy")
    vpn_server = data.get("vpn_server")
    url = data.get("url") or "https://www.ident.me"

    try:
        session_id = open_chrome(session_id=session_id, proxy=proxy, url=url, vpn_server=vpn_server)
        return jsonify({"session_id": session_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/delete_profile", methods=["POST"])
def delete_profile_route():
    data = request.json or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"status": "error", "message": "session_id is required"}), 400

    success, message = delete_profile(session_id)
    if success:
        return jsonify({"status": "success", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 500

@app.route("/close_chrome", methods=["POST"])
def close_chrome_route():
    data = request.json or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"status": "error", "message": "session_id is required"}), 400

    success, message = close_chrome(session_id)
    if success:
        return jsonify({"status": "success", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 500


@app.route("/status")
def status():
    sessions = get_sessions()
    # Refresh statuses based on PID
    for sid, data in sessions.items():
        if data["status"] == "OPEN":
            if not is_pid_alive(data.get("pid")):
                update_session(sid, {"status": "CLOSED"})
    
    # Reload after updates
    return jsonify(get_sessions())


def start_flask():
    app.run(debug=False)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        # Run in dev mode (debug=True)
        app.run(debug=True)
    else:
        # Normal desktop mode (thread + webview)
        threading.Thread(target=lambda: app.run(debug=False), daemon=True).start()
        webview.create_window("Chrome Controller", "http://127.0.0.1:5000")
        webview.start()

