import os
from dotenv import load_dotenv

# Charge les variables du fichier .env
load_dotenv()

SERVER_NAME = os.environ.get("SERVER_NAME", "Horus Panel")

RCON_DATA = {
    'host': os.environ.get("RCON_DATA_HOST", "127.0.0.1"),
    'pass': os.environ.get("RCON_DATA_PASS", ""),
    'port': os.environ.get("RCON_DATA_PORT", "25575")
}

RANK_WEIGHTS = {
    'vanibels': 300,
    'gerant': 200, 'administrateur': 190, 'responsable': 180, 'haut-staff': 175,
    'developpeur': 170, 'graphiste': 160, 'builder': 150, 'creation': 140,
    'communication': 130, 's-modo': 130, 'operateur': 125, 'moderateur_prime': 122,
    'moderateur': 120, 'assistant_prime': 115, 'assistant': 110, 'staff': 105,
    'superstar': 50, 'divin_prime': 47, 'divin': 45, 'empereur_prime': 45,
    'empereur': 40, 'shogun_prime': 35, 'shogun': 30, 'bushi_prime': 25,
    'bushi': 20, 'daymio_prime': 15, 'daymio': 10, 'default_prime': 5, 'default': 0
}

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-placeholder-123")

PANEL_ADMIN = {
    'pseudo': os.environ.get("ADMIN_PSEUDO", "Vanibels"),
    'password': os.environ.get("ADMIN_PASSWORD", "password123")
}