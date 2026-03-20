from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client
import os, datetime

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


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

    row = {
        "quest_id": quest_id,
        "side": side,
        "confidence": int(confidence),
        "logic": logic.strip(),
    }

    result = supabase.table("submissions").insert(row).execute()

    return jsonify({"ok": True, "entry": result.data[0]}), 201


@app.route("/api/stats/<quest_id>")
def stats(quest_id):
    rows = supabase.table("submissions").select("side,confidence").eq("quest_id", quest_id).execute().data
    red = [r["confidence"] for r in rows if r["side"] == "RED"]
    blue = [r["confidence"] for r in rows if r["side"] == "BLUE"]
    return jsonify({
        "total": len(rows),
        "red": {"count": len(red), "avg_conf": round(sum(red) / len(red), 1) if red else 0},
        "blue": {"count": len(blue), "avg_conf": round(sum(blue) / len(blue), 1) if blue else 0},
    })


@app.route("/api/board/<quest_id>")
def board(quest_id):
    rows = supabase.table("submissions").select("side,confidence,logic,submitted_at").eq("quest_id", quest_id).order("submitted_at", desc=True).execute().data
    return jsonify({"entries": rows})


@app.route("/")
def index():
    return send_from_directory(".", "FateCatcher.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
