from pathlib import Path
import os
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

load_dotenv(ROOT_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "atlas_violencia")

ATLAS_HOMENS = BRONZE_DIR / "homicidios_homens.csv"
ATLAS_MULHERES = BRONZE_DIR / "homicidios_mulheres.csv"
SIDRA_5919 = BRONZE_DIR / "tabela5919.csv"
IBGE_MUNICIPIOS_JSON = BRONZE_DIR / "ibge_municipios.json"
IBGE_ESTADOS_JSON = BRONZE_DIR / "ibge_estados.json"
