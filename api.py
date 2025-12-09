from flask import Flask, request, jsonify, render_template
import pandas as pd
import re
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ============================================================
# Chargement du dataset
# ============================================================

DATA_PATH = "Feuille 1-Tableau 1_expectancy.csv"
df = pd.read_csv(DATA_PATH, sep=";")

# Debug : afficher les colonnes dans le terminal
print("Colonnes du CSV :", df.columns.tolist())

# Normalisation des noms de colonnes
df.columns = [c.strip() for c in df.columns]

AVAILABLE_YEARS = sorted(df["year_id"].unique())
AVAILABLE_LOCATIONS = df["location_name"].unique()
DEFAULT_YEAR = 2023 if 2023 in AVAILABLE_YEARS else max(AVAILABLE_YEARS)

# ============================================================
# Dossier pour les images uploadées
# ============================================================

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================================================
# Fonctions d'analyse du texte
# ============================================================

def detect_birth_year(text):
    pattern = r"(19[0-9]{2}|20[0-2][0-9])"
    matches = re.findall(pattern, text)
    if not matches:
        return None
    current_year = datetime.now().year
    for m in matches:
        y = int(m)
        if 1900 <= y <= current_year:
            return y
    return None


def detect_age(text):
    pattern = r"(\d{1,3})\s*ans"
    matches = re.findall(pattern, text)
    if not matches:
        return None
    candidates = [int(x) for x in matches if 0 < int(x) < 120]
    return candidates[0] if candidates else None


def estimate_age(text):
    text = text.lower()
    current_year = datetime.now().year

    age_direct = detect_age(text)
    birth_year = detect_birth_year(text)

    if age_direct is not None:
        return age_direct

    if birth_year is not None:
        age = current_year - birth_year
        if 0 < age < 120:
            return age

    return None


def detect_location(text):
    text = text.lower()
    for loc in AVAILABLE_LOCATIONS:
        if loc.lower() in text:
            return loc
    if "france" in text:
        return "France"
    if "italie" in text or "italy" in text:
        return "Italy"
    if "espagne" in text or "spain" in text:
        return "Spain"
    if "allemagne" in text or "germany" in text:
        return "Germany"
    return "Global"

# ============================================================
# Espérance de vie
# ============================================================

def get_life_expectancy(location, year=None):
    if year is None:
        year = DEFAULT_YEAR

    tmp = df[df["location_name"].str.lower() == location.lower()]
    if tmp.empty:
        return None

    sub = tmp[
        (tmp["year_id"] == year) &
        (tmp["scenario_name"] == "Reference")
    ]
    if sub.empty:
        return None

    row = sub.iloc[0]

    # Recherche automatique des colonnes "years" et "weeks"
    years_col = None
    weeks_col = None

    for col in df.columns:
        col_norm = col.lower().replace(" ", "").replace("_", "")
        if "expectancy" in col_norm and "year" in col_norm:
            years_col = col
        if "expectancy" in col_norm and "week" in col_norm:
            weeks_col = col

    if years_col is None or weeks_col is None:
        raise KeyError(
            f"Colonnes d'espérance de vie introuvables. Colonnes disponibles : {df.columns.tolist()}"
        )

    years = float(row[years_col])
    weeks = float(row[weeks_col])

    return years, weeks


def compute_remaining_life(expectancy_years, age):
    remaining_years = max(expectancy_years - age, 0)
    remaining_weeks = remaining_years * 52
    return remaining_years, remaining_weeks

# ============================================================
# Fonction d'analyse "factice" de la photo
# ============================================================

def generate_text_from_image(image_path):
    """
    Cette fonction ne fait PAS une vraie analyse de santé.
    Elle génère un texte générique comme base que l’utilisateur ajustera.
    """
    return (
        "Je suis une personne adulte vivant dans un environnement urbain. "
        "Mon style de vie semble équilibré, entre travail/études et moments sociaux. "
        "Je fais parfois attention à ma santé, même si je pourrais améliorer "
        "certains aspects comme le sommeil, l’alimentation ou l'activité physique.\n\n"
        "Âge : ?? ans\n"
        "Pays : ??\n"
        "Habitudes : sport, tabac, alcool, stress, etc."
    )

# ============================================================
# ROUTE PRINCIPALE
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    warning = None
    input_text = ""

    if request.method == "POST":
        action = request.form.get("action")
        input_text = request.form.get("user_text", "")

        # --- 1) ANALYSE PHOTO ---
        if action == "analyze_photo":
            photo = request.files.get("photo")
            if photo and photo.filename:
                filename = secure_filename(photo.filename)
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                photo.save(save_path)

                input_text = generate_text_from_image(save_path)
            else:
                warning = "Merci d'ajouter une photo avant d'appuyer sur le bouton."

        # --- 2) PRÉDICTION ---
        elif action == "predict":
            if not input_text.strip():
                warning = "Veuillez écrire ou générer un texte."
            else:
                location = detect_location(input_text)
                age = estimate_age(input_text)
                life = get_life_expectancy(location)

                if life is None:
                    warning = f"Aucune donnée trouvée pour {location}."
                else:
                    years, weeks = life
                    result = {
                        "location": location,
                        "year": DEFAULT_YEAR,
                        "life_expectancy_years": years,
                        "life_expectancy_weeks": int(weeks),
                        "age": age,
                    }

                    if age is not None:
                        rem_years, rem_weeks = compute_remaining_life(years, age)
                        result["remaining_years"] = rem_years
                        result["remaining_weeks"] = int(rem_weeks)
                    else:
                        result["remaining_years"] = None
                        result["remaining_weeks"] = None

    return render_template(
        "index.html",
        result=result,
        warning=warning,
        input_text=input_text
    )

# ============================================================
# LANCEMENT SERVEUR
# ============================================================

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Render a besoin que l'app écoute sur 0.0.0.0 et sur le port donné par $PORT
    app.run(host="0.0.0.0", port=port)
