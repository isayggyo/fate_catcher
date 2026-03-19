from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json, os, datetime

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

SUBMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "submissions.json")


def _load_submissions():
    if os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_submissions(data):
    with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/api/submit", methods=["POST"])
def submit():
    body = request.get_json(force=True)

    quest_id = body.get("questId")
    side = body.get("side")
    confidence = body.get("confidence")
    logic = body.get("logic", "")

    if not quest_id or side not in ("RED", "BLUE"):
        return jsonify({"error": "questId and side(RED/BLUE) required"}), 400
    if not isinstance(confidence, (int, float)) or not (51 <= confidence <= 100):
        return jsonify({"error": "confidence must be 51-100"}), 400
    if len(logic.strip()) < 30:
        return jsonify({"error": "logic must be at least 30 characters"}), 400

    entry = {
        "questId": quest_id,
        "side": side,
        "confidence": int(confidence),
        "logic": logic.strip(),
        "submittedAt": datetime.datetime.utcnow().isoformat() + "Z",
    }

    subs = _load_submissions()
    subs.append(entry)
    _save_submissions(subs)

    return jsonify({"ok": True, "entry": entry}), 201


@app.route("/")
def index():
    return send_from_directory(".", "FateCatcher.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
