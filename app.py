from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)

DATA_FILE = os.environ.get("DATA_FILE", os.path.join(BASE_DIR, "data.json"))


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"tickets": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def gen_id():
    return "T" + str(uuid.uuid4())[:5].upper()


# --- SERVE FRONTEND ---
@app.route("/")
def index():
    return render_template("index.html")


# --- DEBUG ROUTE ---
@app.route("/debug")
def debug():
    static_dir = os.path.join(BASE_DIR, "static")
    templates_dir = os.path.join(BASE_DIR, "templates")
    return jsonify({
        "base_dir": BASE_DIR,
        "base_files": os.listdir(BASE_DIR),
        "static_files": os.listdir(static_dir) if os.path.exists(static_dir) else [],
        "templates_files": os.listdir(templates_dir) if os.path.exists(templates_dir) else [],
    })


# --- TICKETS ---
@app.route("/api/tickets", methods=["GET"])
def get_tickets():
    data = load_data()
    return jsonify(data["tickets"])


@app.route("/api/tickets", methods=["POST"])
def create_ticket():
    body = request.get_json()
    if not body.get("customerName"):
        return jsonify({"error": "Ime kupca je obavezno"}), 400
    if not body.get("items"):
        return jsonify({"error": "Odaberite bar jedan proizvod"}), 400

    ticket = {
        "id": gen_id(),
        "customerName": body["customerName"],
        "phone": body.get("phone", ""),
        "items": body["items"],
        "note": body.get("note", ""),
        "status": "nova",
        "createdAt": datetime.utcnow().isoformat() + "Z",
        "comments": [],
    }
    data = load_data()
    data["tickets"].insert(0, ticket)
    save_data(data)
    return jsonify(ticket), 201


@app.route("/api/tickets/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    data = load_data()
    t = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
    if not t:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    return jsonify(t)


@app.route("/api/tickets/<ticket_id>", methods=["PATCH"])
def update_ticket(ticket_id):
    body = request.get_json()
    data = load_data()
    t = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
    if not t:
        return jsonify({"error": "Tiket nije pronađen"}), 404

    allowed = {"status", "note", "customerName", "phone", "items"}
    for k, v in body.items():
        if k in allowed:
            t[k] = v

    save_data(data)
    return jsonify(t)


@app.route("/api/tickets/<ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id):
    data = load_data()
    before = len(data["tickets"])
    data["tickets"] = [t for t in data["tickets"] if t["id"] != ticket_id]
    if len(data["tickets"]) == before:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    save_data(data)
    return jsonify({"ok": True})


# --- COMMENTS ---
@app.route("/api/tickets/<ticket_id>/comments", methods=["POST"])
def add_comment(ticket_id):
    body = request.get_json()
    if not body.get("text", "").strip():
        return jsonify({"error": "Komentar ne može biti prazan"}), 400

    data = load_data()
    t = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
    if not t:
        return jsonify({"error": "Tiket nije pronađen"}), 404

    author = body.get("author", "Radionica")
    comment = {
        "id": str(uuid.uuid4())[:8],
        "author": author,
        "initials": "".join(w[0].upper() for w in author.split()[:2]),
        "text": body["text"].strip(),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    t["comments"].append(comment)
    save_data(data)
    return jsonify(comment), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
