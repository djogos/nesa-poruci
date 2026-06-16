from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import json
import os
import uuid
from datetime import datetime
from pymongo import MongoClient
import certifi

# MONGO_URI = os.environ.get("MONGO_URI")
MONGO_URI = "mongodb+srv://djjevremovic_db_user:2oBhEZwpKOmFTl5l@cluster0.ykevmuk.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["nesa"]
tickets_collection = db["orders"]
products_collection = db["products"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)


def load_data():
    cursor = tickets_collection.find({}, {"_id": 0}).sort("createdAt", -1)
    return {"tickets": list(cursor)}


def save_data(data):
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
    return jsonify(
        {
            "base_dir": BASE_DIR,
            "base_files": os.listdir(BASE_DIR),
            "static_files": os.listdir(static_dir)
            if os.path.exists(static_dir)
            else [],
            "templates_files": os.listdir(templates_dir)
            if os.path.exists(templates_dir)
            else [],
        }
    )


# --- PRODUCTS ---
@app.route("/api/products", methods=["GET"])
def get_products():
    """
    Returns all products that are in_stock, sorted by category then name.
    Only returns products with tip='simple' or tip='variable' (parent products).
    Excludes child variants (roditelj_id != None).
    """
    cursor = products_collection.find(
        {"u_stanju": True, "roditelj_id": None}, {"_id": 0}
    ).sort([("kategorije", 1), ("naziv", 1)])
    products = list(cursor)
    return jsonify(products)


# --- PRODUCT VARIANTS (children) ---
@app.route("/api/products/variants", methods=["GET"])
def get_variants():
    """
    Returns all child variant products (roditelj_id != None).
    Frontend uses these to look up variant prices by (roditelj_id, atributi match).
    """
    cursor = products_collection.find(
        {"roditelj_id": {"$ne": None}}, {"_id": 0}
    ).sort([("roditelj_id", 1)])
    return jsonify(list(cursor))


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
        "address": body.get("address", ""),
        "apt": body.get("apt", ""),
        "city": body.get("city", ""),
        "items": body["items"],   # each: {woo_id, naziv, sku, qty, cena, customPrice, finalPrice, variant, isCustom}
        "total": body.get("total", 0),
        "note": body.get("note", ""),
        "status": "nova",
        "createdAt": datetime.utcnow().isoformat() + "Z",
        "comments": [],
    }

    tickets_collection.insert_one(ticket)
    ticket.pop("_id", None)
    return jsonify(ticket), 201


@app.route("/api/tickets/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    t = tickets_collection.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    return jsonify(t)


@app.route("/api/tickets/<ticket_id>", methods=["PATCH"])
def update_ticket(ticket_id):
    body = request.get_json()
    allowed = {"status", "note", "customerName", "phone", "items", "address", "apt", "city", "total"}
    update_fields = {k: v for k, v in body.items() if k in allowed}

    if not update_fields:
        return jsonify({"error": "Nema validnih polja za izmenu"}), 400

    result = tickets_collection.find_one_and_update(
        {"id": ticket_id}, {"$set": update_fields}, {"_id": 0}, return_document=True
    )

    if not result:
        return jsonify({"error": "Tiket nije pronađen"}), 404

    return jsonify(result)


@app.route("/api/tickets/<ticket_id>/packed", methods=["PUT"])
def set_packed(ticket_id):
    """Store which item indices are packed. Body: { "packed": [0, 2, 3] }"""
    body = request.get_json()
    packed = body.get("packed", [])
    if not isinstance(packed, list):
        return jsonify({"error": "packed mora biti lista"}), 400
    # Validate: list of ints
    packed = [int(x) for x in packed if str(x).lstrip("-").isdigit()]
    result = tickets_collection.find_one_and_update(
        {"id": ticket_id},
        {"$set": {"packed_items": packed}},
        {"_id": 0},
        return_document=True
    )
    if not result:
        return jsonify({"error": "Tiket nije pronađen"}), 404
    return jsonify({"ok": True, "packed": packed})


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

    result = tickets_collection.update_one(
        {"id": ticket_id}, {"$push": {"comments": comment}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Tiket nije pronađen"}), 404

    return jsonify(comment), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
