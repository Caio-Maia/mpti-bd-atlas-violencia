"""Aplicação de visualização (Seção 8) — Observatório da Violência.

Servidor Flask leve que expõe as consultas Q1–Q7 (src/queries.py) executadas ao
vivo no MongoDB e serve o painel estático em web/. Cada endpoint devolve tanto o
*resultado* quanto a *consulta* (pipeline/filtro) realmente enviada ao banco, de
modo que a interface possa evidenciar o uso efetivo do MongoDB.

Execução:
    python src/app.py            # http://127.0.0.1:5000
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import queries as Q
from config import MONGO_DB

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pretty(query) -> str:
    """Serializa um pipeline/filtro para exibição na interface."""
    return json.dumps(query, ensure_ascii=False, indent=2)


def _envelope(colecao: str, operacao: str, query, resultado: list) -> dict:
    """Resposta padrão: a consulta executada + o resultado vivo."""
    return {
        "colecao": colecao,
        "operacao": operacao,
        "consulta": _pretty(query),
        "n": len(resultado),
        "resultado": resultado,
    }


def _int(nome: str, padrao: int) -> int:
    try:
        return int(request.args.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao


def _float(nome: str, padrao: float) -> float:
    try:
        return float(request.args.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao


# --------------------------------------------------------------------------- #
# Estáticos (SPA)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:caminho>")
def estaticos(caminho: str):
    return send_from_directory(WEB_DIR, caminho)


# --------------------------------------------------------------------------- #
# Metadados que alimentam os controles da interface
# --------------------------------------------------------------------------- #
@app.get("/api/meta")
def meta():
    db = Q.get_db()

    # Anos que possuem taxa de homicídios calculada (dependem da população SIDRA).
    anos_taxa = db.municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.taxaHomicidiosPor100k": {"$ne": None}}},
        {"$group": {"_id": "$seriesAnuais.ano"}},
        {"$sort": {"_id": 1}},
    ])
    anos_taxa = [a["_id"] for a in anos_taxa]

    # Faixa completa de anos com contagem de homicídios (cobre todos os municípios).
    faixa = list(db.municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$group": {"_id": None, "min": {"$min": "$seriesAnuais.ano"}, "max": {"$max": "$seriesAnuais.ano"}}},
    ]))
    anos_contagem = faixa[0] if faixa else {"min": None, "max": None}

    # Municípios que possuem taxa (as 27 capitais) — alimentam os seletores Q2/Q7.
    # Precisa de $unwind: num filtro direto, as séries sem taxa (campo removido na
    # carga) contam como null e fariam `$ne: null` rejeitar o documento inteiro.
    capitais = list(db.municipios.aggregate([
        {"$unwind": "$seriesAnuais"},
        {"$match": {"seriesAnuais.taxaHomicidiosPor100k": {"$ne": None}}},
        {"$group": {"_id": {
            "codIBGE": "$codIBGE", "nome": "$nome",
            "siglaUF": "$siglaUF", "nomeRegiao": "$nomeRegiao",
        }}},
        {"$replaceRoot": {"newRoot": "$_id"}},
        {"$sort": {"nome": 1}},
    ]))

    regioes = list(db.regioes.find({}, {"_id": 1, "sigla": 1, "nome": 1}).sort("nome", 1))
    fontes = list(db.fontes.find({}, {"_id": 1, "nome": 1, "origem": 1, "portal": 1}))

    return jsonify({
        "db": MONGO_DB,
        "anosTaxa": anos_taxa,
        "anosContagem": anos_contagem,
        "capitais": capitais,
        "regioes": regioes,
        "fontes": fontes,
        "totalMunicipios": db.municipios.estimated_document_count(),
    })


# --------------------------------------------------------------------------- #
# Q1–Q7
# --------------------------------------------------------------------------- #
@app.get("/api/q1")
def api_q1():
    ano = _int("ano", 2022)
    limite = _int("limite", 10)
    pipeline = Q.q1_pipeline(ano, limite)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


@app.get("/api/q2")
def api_q2():
    cod = _int("cod", 2507507)
    ini = _int("ini", 2012)
    fim = _int("fim", 2022)
    pipeline = Q.q2_pipeline(cod, ini, fim)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


@app.get("/api/q3")
def api_q3():
    ano = _int("ano", 2022)
    pipeline = Q.q3_pipeline(ano)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


@app.get("/api/q4")
def api_q4():
    ano = _int("ano", 2022)
    limite = _int("limite", 200)
    pipeline = Q.q4_pipeline(ano, limite)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


@app.get("/api/q5")
def api_q5():
    taxa_min = _float("taxa_min", 30)
    esc_max = _float("esc_max", 60)
    filtro, projecao = Q.q5_query(taxa_min, esc_max)
    resultado = list(Q.get_db().municipios.find(filtro, projecao).limit(50))
    return jsonify(_envelope("municipios", "find",
                             {"filtro": filtro, "projeção": projecao}, resultado))


@app.get("/api/q6")
def api_q6():
    ano = _int("ano", 2022)
    pipeline = Q.q6_pipeline(ano)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


@app.get("/api/q7")
def api_q7():
    cod = _int("cod", 2507507)
    ano = _int("ano", 2022)
    pipeline = Q.q7_pipeline(cod, ano)
    return jsonify(_envelope("municipios", "aggregate", pipeline,
                             list(Q.get_db().municipios.aggregate(pipeline))))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
