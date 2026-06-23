from __future__ import annotations

from pprint import pprint
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import MONGO_URI, MONGO_DB

PIPELINE_Q1 = [
    {"$unwind": "$seriesAnuais"},
    {"$match": {"seriesAnuais.ano": 2022, "seriesAnuais.taxaHomicidiosPor100k": {"$ne": None}}},
    {"$sort": {"seriesAnuais.taxaHomicidiosPor100k": -1}},
    {"$limit": 10},
]


def run_explain_demo() -> None:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]

    print("Removendo índice composto para demonstrar COLLSCAN...")
    try:
        db.municipios.drop_index("idx_esr_ano_taxa")
    except Exception:
        pass

    explain_sem = db.command("aggregate", "municipios", pipeline=PIPELINE_Q1, explain=True)
    print("\nEXPLAIN SEM ÍNDICE COMPOSTO")
    pprint(explain_sem)

    print("\nCriando índice composto ESR...")
    db.municipios.create_index(
        [("seriesAnuais.ano", ASCENDING), ("seriesAnuais.taxaHomicidiosPor100k", DESCENDING)],
        name="idx_esr_ano_taxa",
    )

    explain_com = db.command("aggregate", "municipios", pipeline=PIPELINE_Q1, explain=True)
    print("\nEXPLAIN COM ÍNDICE COMPOSTO")
    pprint(explain_com)


if __name__ == "__main__":
    run_explain_demo()
