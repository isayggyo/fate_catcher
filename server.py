from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client
from functools import wraps
from collections import defaultdict
import os, datetime

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


# ── AUTH ──────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(force=True)
    email = body.get("email", "").strip()
    password = body.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return jsonify({
            "access_token": res.session.access_token,
            "user_id": res.user.id,
            "email": res.user.email,
        })
    except Exception as e:
        return jsonify({"error": "Invalid email or password"}), 401


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization required"}), 401
        token = auth_header[7:]
        try:
            user = supabase.auth.get_user(token)
            request.user_id = user.user.id
            request.user_email = user.user.email
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(*args, **kwargs)
    return decorated


# ── QUESTS ────────────────────────────────────────────

@app.route("/api/quests")
def quests():
    rows = supabase.table("quests").select("*").eq("active", True).order("deadline").execute().data
    return jsonify({"quests": rows})


# ── SUBMIT ────────────────────────────────────────────

@app.route("/api/submit", methods=["POST"])
@require_auth
def submit():
    try:
        body = request.get_json(force=True)
        user_id = request.user_id

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

        # Check for existing submission by this user for this quest
        existing = supabase.table("submissions").select("id").eq("quest_id", quest_id).eq("user_id", str(user_id)).execute().data
        if existing:
            # Update existing submission
            supabase.table("submissions").update({
                "side": side,
                "confidence": int(confidence),
                "logic": logic.strip(),
            }).eq("id", existing[0]["id"]).execute()
            updated = supabase.table("submissions").select("*").eq("id", existing[0]["id"]).execute()
            return jsonify({"ok": True, "entry": updated.data[0], "updated": True}), 200

        row = {
            "quest_id": quest_id,
            "side": side,
            "confidence": int(confidence),
            "logic": logic.strip(),
            "user_id": str(user_id),
        }

        result = supabase.table("submissions").insert(row).execute()

        return jsonify({"ok": True, "entry": result.data[0]}), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── STATS ─────────────────────────────────────────────

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


# ── BOARD ─────────────────────────────────────────────

def _get_user_id_from_token():
    """Try to extract user_id from Authorization header. Returns None if not authenticated."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        return None


def _attach_votes(rows, user_id):
    """Attach up/down counts and my_vote to each row in a single bulk query."""
    if not rows:
        return rows
    sub_ids = [r["id"] for r in rows]
    # 1 query: fetch all votes for these submissions
    all_votes = supabase.table("votes").select("submission_id,vote_type,user_id").in_("submission_id", sub_ids).execute().data
    # aggregate in Python
    up_counts = defaultdict(int)
    down_counts = defaultdict(int)
    my_votes = {}
    for v in all_votes:
        if v["vote_type"] == "up":
            up_counts[v["submission_id"]] += 1
        else:
            down_counts[v["submission_id"]] += 1
        if user_id and v["user_id"] == user_id:
            my_votes[v["submission_id"]] = v["vote_type"]
    for row in rows:
        row["up"] = up_counts[row["id"]]
        row["down"] = down_counts[row["id"]]
        row["my_vote"] = my_votes.get(row["id"])
        row["is_mine"] = (row.get("user_id") == user_id) if user_id else False
        row.pop("user_id", None)
    return rows


@app.route("/api/board-all")
def board_all():
    user_id = _get_user_id_from_token()
    rows = supabase.table("submissions").select("id,quest_id,side,confidence,logic,submitted_at,user_id").order("submitted_at", desc=True).execute().data
    rows = _attach_votes(rows, user_id)
    return jsonify({"entries": rows})


@app.route("/api/board/<quest_id>")
def board(quest_id):
    user_id = _get_user_id_from_token()
    rows = supabase.table("submissions").select("id,side,confidence,logic,submitted_at,user_id").eq("quest_id", quest_id).order("submitted_at", desc=True).execute().data
    rows = _attach_votes(rows, user_id)
    return jsonify({"entries": rows})


# ── VOTE ──────────────────────────────────────────────

@app.route("/api/vote", methods=["POST"])
@require_auth
def vote():
    body = request.get_json(force=True)
    submission_id = body.get("submissionId")
    vote_type = body.get("voteType")
    if not submission_id or vote_type not in ("up", "down", "cancel"):
        return jsonify({"error": "submissionId and voteType(up/down/cancel) required"}), 400
    user_id = request.user_id
    if vote_type == "cancel":
        supabase.table("votes").delete().eq("submission_id", submission_id).eq("user_id", user_id).execute()
    else:
        row = {"submission_id": submission_id, "vote_type": vote_type, "user_id": user_id}
        try:
            supabase.table("votes").insert(row).execute()
        except Exception:
            supabase.table("votes").update({"vote_type": vote_type}).eq("submission_id", submission_id).eq("user_id", user_id).execute()
    return jsonify({"ok": True}), 201


# ── PAGES ─────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "FateCatcher.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
