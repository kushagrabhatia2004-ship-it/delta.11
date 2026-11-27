
import os
import joblib
import pandas as pd
from flask import Flask, render_template, request, jsonify
from early_warning_system import (generate_data, train_models, early_warning,
                                  recommend_fertilizer, CROP_N_DEMAND, FEATURES)
from alerts import format_alert, send_alert

app = Flask(__name__)

if os.path.exists("runoff_models.joblib"):
    MODELS = joblib.load("runoff_models.joblib")
else:
    MODELS = train_models(generate_data())


def parse_field(data):
    try:
        field = {k: float(data[k]) for k in FEATURES}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Missing or invalid input: {e}")
    field["rain_72h_mm"] = max(field["rain_72h_mm"], field["rain_24h_mm"])
    return field


# ---------------- pages ----------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", crops=list(CROP_N_DEMAND))


@app.route("/how-it-works")
def how():
    return render_template("how.html", features=FEATURES, crops=CROP_N_DEMAND)


@app.route("/about")
def about():
    return render_template("about.html")


# ---------------- API ----------------
@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    try:
        field = parse_field(data)
        crop = data.get("crop", "wheat")
        if crop not in CROP_N_DEMAND:
            raise ValueError("Unknown crop")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    warning = early_warning(MODELS, field)
    rec = recommend_fertilizer(crop, field["soil_N_ppm"], field["rain_72h_mm"],
                               warning["nitrogen_risk"])
    return jsonify({"warning": warning, "recommendation": rec})


@app.route("/api/sensitivity", methods=["POST"])
def sensitivity():
    """Risk for rainfall 0..150 mm with the other inputs held fixed (for the chart)."""
    try:
        field = parse_field(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    rains = list(range(0, 151, 10))
    rows = [{**field, "rain_24h_mm": r, "rain_72h_mm": max(r, field["rain_72h_mm"])}
            for r in rains]
    X = pd.DataFrame(rows)[FEATURES]
    n = MODELS["n_runoff_risk"].predict(X).clip(0, 1)
    p = MODELS["pest_runoff_risk"].predict(X).clip(0, 1)
    return jsonify({"rain": rains, "nitrogen": [round(float(v), 3) for v in n],
                    "pesticide": [round(float(v), 3) for v in p]})


@app.route("/api/alert", methods=["POST"])
def alert():
    data = request.get_json(silent=True) or {}
    try:
        field = parse_field(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    phone = str(data.get("phone", "")).strip()
    if len(phone) < 8 or not phone.startswith("+"):
        return jsonify({"error": "Enter the phone number with country code, e.g. +91XXXXXXXXXX"}), 400
    warning = early_warning(MODELS, field)
    sent, info = send_alert(phone, format_alert("My Field", warning),
                            whatsapp=bool(data.get("whatsapp")))
    return jsonify({"sent": sent, "message": info})
if __name__ == "__main__":
    app.run(debug=True)
