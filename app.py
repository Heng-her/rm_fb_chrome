from flask import Flask, jsonify, render_template, request
import threading
import webview

from core.chrome_manager import open_chrome, close_chrome
from core.session_store import get_sessions

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/open_chrome", methods=["POST"])
def open_chrome_route():
    data = request.json or {}
    session_id = data.get("session_id")

    session_id = open_chrome(session_id=session_id)
    return jsonify({"session_id": session_id})

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

