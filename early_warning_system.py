"""
AI-Assisted Early Warning System for Precision Fertilizer Management
and Pesticide Runoff Mitigation

Pipeline:
 1. Generate synthetic field data (replace with real sensor/weather/soil data)
 2. Train ML models to predict nitrogen and pesticide runoff risk (0-1)
 3. Recommend fertilizer rate and timing (precision management)
 4. Issue early warnings with mitigation actions from rainfall forecasts

Run:  pip install numpy pandas scikit-learn joblib
      python early_warning_system.py
"""
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

RNG = np.random.default_rng(42)

FEATURES = [
    "soil_moisture",        # volumetric fraction 0-0.5
    "soil_N_ppm",           # soil nitrate nitrogen
    "clay_fraction",        # 0-1
    "slope_pct",            # field slope %
    "rain_24h_mm",          # forecast rainfall next 24 h
    "rain_72h_mm",          # forecast rainfall next 72 h
    "days_since_fert",      # days since last fertilizer
    "fert_rate_kgN_ha",     # last applied N rate
    "days_since_pest",      # days since last pesticide spray
    "pest_rate_kg_ha",      # pesticide active ingredient rate
    "buffer_strip_m",       # vegetative buffer width
    "dist_to_water_m",      # distance to nearest stream/pond
]


# ----------------------------------------------------------------------
# 1. Synthetic data (physically-inspired runoff relationships + noise)
# ----------------------------------------------------------------------
def generate_data(n=6000):
    df = pd.DataFrame({
        "soil_moisture": RNG.uniform(0.08, 0.45, n),
        "soil_N_ppm": RNG.uniform(5, 60, n),
        "clay_fraction": RNG.uniform(0.05, 0.6, n),
        "slope_pct": RNG.uniform(0, 15, n),
        "rain_24h_mm": RNG.gamma(1.2, 12, n).clip(0, 150),
        "rain_72h_mm": 0,
        "days_since_fert": RNG.integers(0, 60, n),
        "fert_rate_kgN_ha": RNG.uniform(0, 180, n),
        "days_since_pest": RNG.integers(0, 45, n),
        "pest_rate_kg_ha": RNG.uniform(0, 3, n),
        "buffer_strip_m": RNG.uniform(0, 20, n),
        "dist_to_water_m": RNG.uniform(5, 500, n),
    })
    df["rain_72h_mm"] = df["rain_24h_mm"] + RNG.gamma(1.5, 10, n)

    # Runoff generation (curve-number-like): wet, clayey, steep soils shed water
    runoff_coef = (0.35 * (df.soil_moisture / 0.45) + 0.35 * df.clay_fraction
                   + 0.30 * (df.slope_pct / 15))
    rain_term = 1 / (1 + np.exp(-(df.rain_24h_mm - 25) / 10))
    runoff = runoff_coef * rain_term

    # Source term: recent, high-rate applications are most mobile
    n_source = (df.fert_rate_kgN_ha / 180) * np.exp(-df.days_since_fert / 20) \
        + 0.4 * df.soil_N_ppm / 60
    p_source = (df.pest_rate_kg_ha / 3) * np.exp(-df.days_since_pest / 12)

    # Mitigation: buffers and distance to water attenuate delivery
    attenuation = np.exp(-df.buffer_strip_m / 10) * (0.5 + 0.5 * np.exp(-df.dist_to_water_m / 200))

    df["n_runoff_risk"] = (runoff * n_source * attenuation * 3.0
                           + RNG.normal(0, 0.02, n)).clip(0, 1)
    df["pest_runoff_risk"] = (runoff * p_source * attenuation * 3.5
                              + RNG.normal(0, 0.02, n)).clip(0, 1)
    return df


# ----------------------------------------------------------------------
# 2. Model training
# ----------------------------------------------------------------------
def train_models(df):
    X_train, X_test, idx_train, idx_test = train_test_split(
        df[FEATURES], df.index, test_size=0.2, random_state=1)
    models = {}
    for target in ["n_runoff_risk", "pest_runoff_risk"]:
        model = GradientBoostingRegressor(n_estimators=300, max_depth=4,
                                          learning_rate=0.05, random_state=1)
        model.fit(X_train, df.loc[idx_train, target])
        pred = model.predict(X_test)
        print(f"[{target}] MAE={mean_absolute_error(df.loc[idx_test, target], pred):.3f} "
              f"R2={r2_score(df.loc[idx_test, target], pred):.3f}")
        models[target] = model
    joblib.dump(models, "runoff_models.joblib")
    return models


# ----------------------------------------------------------------------
# 3. Precision fertilizer recommendation
# ----------------------------------------------------------------------
CROP_N_DEMAND = {"wheat": 120, "rice": 100, "maize": 150, "vegetables": 130}  # kg N/ha

def recommend_fertilizer(crop, soil_N_ppm, rain_72h_mm, n_risk, splits=3):
    """Return rate (kg N/ha) and timing. Soil N ppm ~ 2 kg/ha per ppm (top 15 cm)."""
    soil_supply = soil_N_ppm * 2.0
    deficit = max(CROP_N_DEMAND[crop] - soil_supply, 0)
    per_split = deficit / splits
    if rain_72h_mm > 40 or n_risk > 0.5:
        action, delay = "DELAY application", 3
    elif rain_72h_mm > 20 or n_risk > 0.3:
        action, delay = "Apply reduced dose (-30%)", 0
        per_split *= 0.7
    else:
        action, delay = "Apply now", 0
    return {"total_deficit_kgN_ha": round(deficit, 1),
            "this_application_kgN_ha": round(per_split, 1),
            "action": action, "delay_days": delay}


# ----------------------------------------------------------------------
# 4. Early warning engine
# ----------------------------------------------------------------------
def risk_level(p):
    return "HIGH" if p >= 0.5 else "MEDIUM" if p >= 0.25 else "LOW"

def early_warning(models, field):
    x = pd.DataFrame([field])[FEATURES]
    n_risk = float(models["n_runoff_risk"].predict(x)[0])
    p_risk = float(models["pest_runoff_risk"].predict(x)[0])
    n_lvl, p_lvl = risk_level(n_risk), risk_level(p_risk)

    actions = []
    if n_lvl != "LOW":
        actions += ["Postpone/split nitrogen application until rain passes",
                    "Switch to slow-release or injected fertilizer"]
    if p_lvl != "LOW":
        actions += ["Do not spray pesticide in the next 48 h",
                    "Use low-drift nozzles and spot-treat only"]
    if "HIGH" in (n_lvl, p_lvl):
        actions += ["Install/inspect buffer strips, check silt fences and drains",
                    "Alert downstream water users / monitor stream turbidity"]
    if field["buffer_strip_m"] < 5 and "LOW" not in (n_lvl, p_lvl):
        actions.append("Widen vegetative buffer to at least 10 m")
    if not actions:
        actions = ["Conditions safe — proceed with normal schedule"]

    return {"nitrogen_risk": round(n_risk, 2), "nitrogen_level": n_lvl,
            "pesticide_risk": round(p_risk, 2), "pesticide_level": p_lvl,
            "actions": list(dict.fromkeys(actions))}


# ----------------------------------------------------------------------
# Demo
# ----------------------------------------------------------------------
if __name__ == "__main__":
    data = generate_data()
    models = train_models(data)

    field = {
        "soil_moisture": 0.38, "soil_N_ppm": 22, "clay_fraction": 0.45,
        "slope_pct": 9, "rain_24h_mm": 55, "rain_72h_mm": 80,
        "days_since_fert": 4, "fert_rate_kgN_ha": 120,
        "days_since_pest": 3, "pest_rate_kg_ha": 2.0,
        "buffer_strip_m": 2, "dist_to_water_m": 40,
    }
    warning = early_warning(models, field)
    print("\n=== EARLY WARNING ===")
    for k, v in warning.items():
        print(f"{k}: {v}")

    rec = recommend_fertilizer("wheat", field["soil_N_ppm"], field["rain_72h_mm"],
                               warning["nitrogen_risk"])
    print("\n=== FERTILIZER RECOMMENDATION ===")
    for k, v in rec.items():
        print(f"{k}: {v}")
