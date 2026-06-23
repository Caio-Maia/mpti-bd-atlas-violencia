from __future__ import annotations

from pymongo import MongoClient, ASCENDING, DESCENDING

from config import MONGO_URI, MONGO_DB, GOLD_DIR
from utils import load_json


def create_schema_validation(db) -> None:
    if "municipios" not in db.list_collection_names():
        db.create_collection(
            "municipios",
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["codIBGE", "nome", "seriesAnuais"],
                    "properties": {
                        "codIBGE": {"bsonType": "int"},
                        "nome": {"bsonType": "string"},
                        "seriesAnuais": {
                            "bsonType": "array",
                            "items": {
                                "bsonType": "object",
                                "required": ["ano", "homicidiosTotais", "fonteIds"],
                            },
                        },
                    },
                }
            },
        )


def create_indexes(db) -> None:
    db.municipios.create_index([("codIBGE", ASCENDING)], name="idx_codIBGE", unique=True)
    db.municipios.create_index([("codIBGEStr", ASCENDING)], name="idx_codIBGEStr")
    db.municipios.create_index([("nomeRegiao", ASCENDING)], name="idx_nomeRegiao")
    db.municipios.create_index([("siglaUF", ASCENDING)], name="idx_siglaUF")
    db.municipios.create_index([("seriesAnuais.ano", ASCENDING)], name="idx_series_ano")
    db.municipios.create_index(
        [("seriesAnuais.ano", ASCENDING), ("seriesAnuais.taxaHomicidiosPor100k", DESCENDING)],
        name="idx_esr_ano_taxa",
    )
    db.municipios.create_index(
        [("seriesAnuais.ano", ASCENDING), ("nomeRegiao", ASCENDING)],
        name="idx_ano_regiao",
    )
    db.fontes.create_index([("nome", ASCENDING)], name="idx_fontes_nome")


def replace_collection(db, name: str, documents: list[dict]) -> None:
    db[name].delete_many({})
    if documents:
        db[name].insert_many(documents)


def run_load(drop_database: bool = False) -> None:
    client = MongoClient(MONGO_URI)
    if drop_database:
        client.drop_database(MONGO_DB)
    db = client[MONGO_DB]

    create_schema_validation(db)

    replace_collection(db, "fontes", load_json(GOLD_DIR / "fontes.json"))
    replace_collection(db, "regioes", load_json(GOLD_DIR / "regioes.json"))
    replace_collection(db, "ufs", load_json(GOLD_DIR / "ufs.json"))
    replace_collection(db, "municipios", load_json(GOLD_DIR / "municipios.json"))

    create_indexes(db)

    print("Carga concluída no MongoDB")
    print(f"Banco: {MONGO_DB}")
    for name in ["municipios", "ufs", "regioes", "fontes"]:
        print(f"- {name}: {db[name].count_documents({})} documentos")
