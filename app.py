from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import json
import os
import uuid
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000
)
db = client["nesa"]  # Ime baze podataka
tickets_collection = db["orders"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)

DATA_FILE = os.environ.get("DATA_FILE", os.path.join(BASE_DIR, "data.json"))


def load_data():
    # MongoDB vraća podatke, mi ih pakujemo u format koji tvoj frontend već očekuje
    # Sortiramo ih tako da najnovije porudžbine budu na vrhu
    cursor = tickets_collection.find({}, {"_id": 0}).sort("createdAt", -1)
    return {"tickets": list(cursor)}


def save_data(data):
    # Pošto MongoDB radi sa pojedinačnim unosima, ova funkcija nam tehnički više ne treba za dodavanje,
    # ali je zadržavamo praznu da ti ne bismo kvarili ostatak koda ako se negde poziva.
    pass

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
    
    # DIREKTNO upisujemo u MongoDB
    tickets_collection.insert_one(ticket)
    
    # Sklanjamo MongoDB interni ID pre slanja frontendu
    ticket.pop("_id", None)
    return jsonify(ticket), 201


@app.route("/api/tickets/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    # Tražimo tiket po ID-ju
    t = tickets_collection.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    return jsonify(t)


@app.route("/api/tickets/<ticket_id>", methods=["PATCH"])
def update_ticket(ticket_id):
    body = request.get_json()
    
    allowed = {"status", "note", "customerName", "phone", "items"}
    update_fields = {k: v for k, v in body.items() if k in allowed}
    
    if not update_fields:
        return jsonify({"error": "Nema validnih polja za izmenu"}), 400

    # Menjamo samo poslata polja u bazi
    result = tickets_collection.find_one_and_update(
        {"id": ticket_id},
        {"$set": update_fields},
        {"_id": 0},
        return_document=True # Vraća izmenjen objekat
    )
    
    if not result:
        return jsonify({"error": "Tiket nije pronađen"}), 404
        
    return jsonify(result)


@app.route("/api/tickets/<ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id):
    result = tickets_collection.delete_one({"id": ticket_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    return jsonify({"ok": True})

# --- COMMENTS ---
@app.route("/api/tickets/<ticket_id>/comments", methods=["POST"])
def add_comment(ticket_id):
    body = request.get_json()
    if not body.get("text", "").strip():
        return jsonify({"error": "Komentar ne može biti prazan"}), 400

    author = body.get("author", "Radionica")
    comment = {
        "id": str(uuid.uuid4())[:8],
        "author": author,
        "initials": "".join(w[0].upper() for w in author.split()[:2]),
        "text": body["text"].strip(),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    
    # Direktno guramo (push) komentar u niz "comments" unutar tog tiketa
    result = tickets_collection.update_one(
        {"id": ticket_id},
        {"$push": {"comments": comment}}
    )
    
    if result.matched_count == 0:
        return jsonify({"error": "Tiket nije pronađen"}), 404
        
    return jsonify(comment), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
