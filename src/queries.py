from __future__ import annotations

from pprint import pprint
from pymongo import MongoClient, DESCENDING
from config import MONGO_URI, MONGO_DB


def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]


def q1_top10_municipios_ano(ano: int = 2022):
    return list(get_db().municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.ano": ano, "seriesAnuais.taxaHomicidiosPor100k": {"$ne": None}}},
        {"$sort": {"seriesAnuais.taxaHomicidiosPor100k": -1}},
        {"$limit": 10},
        {"$project": {
            "_id": 0,
            "codIBGE": 1,
            "municipio": "$nome",
            "uf": "$siglaUF",
            "regiao": "$nomeRegiao",
            "ano": "$seriesAnuais.ano",
            "taxaHomicidiosPor100k": "$seriesAnuais.taxaHomicidiosPor100k",
            "homicidiosTotais": "$seriesAnuais.homicidiosTotais",
        }},
    ]))


def q2_evolucao_municipio(cod_ibge: int = 2507507, ano_inicio: int = 2012, ano_fim: int = 2022):
    return list(get_db().municipios.aggregate([
        {"$match": {"codIBGE": cod_ibge}},
        {"$project": {
            "_id": 0,
            "codIBGE": 1,
            "nome": 1,
            "seriesAnuais": {
                "$filter": {
                    "input": "$seriesAnuais",
                    "as": "serie",
                    "cond": {"$and": [
                        {"$gte": ["$$serie.ano", ano_inicio]},
                        {"$lte": ["$$serie.ano", ano_fim]},
                    ]},
                }
            },
        }},
    ]))


def q3_media_regiao_ano(ano: int = 2022):
    return list(get_db().municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.ano": ano, "seriesAnuais.taxaHomicidiosPor100k": {"$ne": None}}},
        {"$group": {
            "_id": "$nomeRegiao",
            "mediaTaxa": {"$avg": "$seriesAnuais.taxaHomicidiosPor100k"},
            "municipios": {"$sum": 1},
        }},
        {"$sort": {"mediaTaxa": -1}},
        {"$project": {"_id": 0, "regiao": "$_id", "mediaTaxa": {"$round": ["$mediaTaxa", 2]}, "municipios": 1}},
    ]))


def q4_scatter_violencia_escolaridade(ano: int = 2022, limite: int = 200):
    return list(get_db().municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {
            "seriesAnuais.ano": ano,
            "seriesAnuais.taxaHomicidiosPor100k": {"$ne": None},
            "seriesAnuais.pctEnsinoMedioOuMais": {"$ne": None},
        }},
        {"$project": {
            "_id": 0,
            "municipio": "$nome",
            "uf": "$siglaUF",
            "taxaHomicidiosPor100k": "$seriesAnuais.taxaHomicidiosPor100k",
            "pctEnsinoMedioOuMais": "$seriesAnuais.pctEnsinoMedioOuMais",
            "populacaoTotal": "$seriesAnuais.populacaoTotal",
        }},
        {"$sort": {"taxaHomicidiosPor100k": -1}},
        {"$limit": limite},
    ]))


def q5_elem_match(taxa_min: float = 50, escolaridade_max: float = 30):
    return list(get_db().municipios.find(
        {"seriesAnuais": {"$elemMatch": {
            "taxaHomicidiosPor100k": {"$gt": taxa_min},
            "pctEnsinoMedioOuMais": {"$lt": escolaridade_max},
        }}},
        {"_id": 0, "codIBGE": 1, "nome": 1, "siglaUF": 1, "seriesAnuais.$": 1},
    ).limit(50))


def q6_bucket_porte_populacional(ano: int = 2022):
    return list(get_db().municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.ano": ano, "seriesAnuais.populacaoTotal": {"$ne": None}}},
        {"$bucket": {
            "groupBy": "$seriesAnuais.populacaoTotal",
            "boundaries": [0, 20, 100, 999999],
            "default": "Outro",
            "output": {
                "municipios": {"$sum": 1},
                "mediaTaxa": {"$avg": "$seriesAnuais.taxaHomicidiosPor100k"},
            },
        }},
        {"$project": {
            "_id": 0,
            "portePopulacional": {"$switch": {
                "branches": [
                    {"case": {"$eq": ["$_id", 0]}, "then": "Pequeno - até 20 mil hab."},
                    {"case": {"$eq": ["$_id", 20]}, "then": "Médio - 20 a 100 mil hab."},
                    {"case": {"$eq": ["$_id", 100]}, "then": "Grande - acima de 100 mil hab."},
                ],
                "default": "Outro",
            }},
            "municipios": 1,
            "mediaTaxa": {"$round": ["$mediaTaxa", 2]},
        }},
    ]))


def q7_lookup_fontes(cod_ibge: int = 2507507, ano: int = 2022):
    return list(get_db().municipios.aggregate([
        {"$match": {"codIBGE": cod_ibge}},
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.ano": ano}},
        {"$lookup": {
            "from": "fontes",
            "localField": "seriesAnuais.fonteIds",
            "foreignField": "_id",
            "as": "fontes",
        }},
        {"$project": {
            "_id": 0,
            "municipio": "$nome",
            "ano": "$seriesAnuais.ano",
            "indicadores": {
                "homicidiosTotais": "$seriesAnuais.homicidiosTotais",
                "taxaHomicidiosPor100k": "$seriesAnuais.taxaHomicidiosPor100k",
                "pctEnsinoMedioOuMais": "$seriesAnuais.pctEnsinoMedioOuMais",
            },
            "fontes.nome": 1,
            "fontes.origem": 1,
            "fontes.portal": 1,
        }},
    ]))


def run_all_examples() -> None:
    examples = [
        ("Q1 - Top 10 municípios", q1_top10_municipios_ano),
        ("Q2 - Evolução João Pessoa", q2_evolucao_municipio),
        ("Q3 - Média por região", q3_media_regiao_ano),
        ("Q4 - Violência x escolaridade", q4_scatter_violencia_escolaridade),
        ("Q5 - elemMatch", q5_elem_match),
        ("Q6 - Bucket porte populacional", q6_bucket_porte_populacional),
        ("Q7 - Lookup fontes", q7_lookup_fontes),
    ]
    for title, fn in examples:
        print("\n" + "=" * 80)
        print(title)
        pprint(fn())


if __name__ == "__main__":
    run_all_examples()
