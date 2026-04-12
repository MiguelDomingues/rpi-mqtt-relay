from flask import Flask, jsonify, send_from_directory
from threading import Thread

import os
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
app = Flask(__name__, static_folder=STATIC_DIR)

# This will be set by the main process to provide live status
data_provider = None

def set_data_provider(provider_func):
    global data_provider
    data_provider = provider_func

def run_web_status():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


@app.route("/status")
def status():
    if data_provider is None:
        return jsonify({"error": "No data provider set"}), 500
    return jsonify(data_provider())

@app.route("/")
def index():
    # Serve the static index.html
    return send_from_directory(app.static_folder, "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

def start_web_status_thread(provider_func):
    set_data_provider(provider_func)
    thread = Thread(target=run_web_status, daemon=True)
    thread.start()
    return thread
