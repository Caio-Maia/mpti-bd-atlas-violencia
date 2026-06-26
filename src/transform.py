from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    ATLAS_HOMENS,
    ATLAS_MULHERES,
    SIDRA_5919,
    IBGE_MUNICIPIOS_JSON,
    IBGE_ESTADOS_JSON,
    SILVER_DIR,
    GOLD_DIR,
)
from utils import ensure_dirs, load_json, save_json, to_float_or_none, round_or_none

FONTE_ATLAS_ID = "atlas_violencia_ipea_fbsp"
FONTE_SIDRA_ID = "ibge_sidra_5919"
FONTE_LOCALIDADES_ID = "ibge_localidades"

NIVEL_MAP = {
    "Total": "total",
    "Sem instrução e menos de 1 ano de estudo": "semInstrucao",
    "Ensino fundamental incompleto ou equivalente": "fundamentalIncompleto",
    "Ensino fundamental completo ou equivalente": "fundamentalCompleto",
    "Ensino médio incompleto ou equivalente": "medioIncompleto",
    "Ensino médio completo ou equivalente": "medioCompleto",
    "Ensino superior incompleto ou equivalente": "superiorIncompleto",
    "Ensino superior completo ou equivalente": "superiorCompleto",
    "Não determinado": "naoDeterminado",
}


def read_atlas(path: Path, value_col: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns={"Região ID": "codIBGE", "Valor": value_col})
    df["ano"] = pd.to_datetime(df["Período"], errors="coerce").dt.year
    df["codIBGE"] = df["codIBGE"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0).astype(int)
    return df[["codIBGE", "ano", value_col]]


def transform_violencia() -> pd.DataFrame:
    homens = read_atlas(ATLAS_HOMENS, "homicidiosHomens")
    mulheres = read_atlas(ATLAS_MULHERES, "homicidiosMulheres")
    violencia = homens.merge(mulheres, on=["codIBGE", "ano"], how="outer")
    violencia["homicidiosHomens"] = violencia["homicidiosHomens"].fillna(0).astype(int)
    violencia["homicidiosMulheres"] = violencia["homicidiosMulheres"].fillna(0).astype(int)
    violencia["homicidiosTotais"] = violencia["homicidiosHomens"] + violencia["homicidiosMulheres"]
    violencia = violencia.drop_duplicates(subset=["codIBGE", "ano"])
    violencia.to_csv(SILVER_DIR / "violencia.csv", index=False)
    return violencia


def normalize_sidra_rows(path: Path) -> list[dict[str, Any]]:
    """Lê o CSV wide da Tabela 5919 e devolve linhas longas por município/trimestre/nível.

    O arquivo SIDRA exportado possui duas linhas de metadados, duas linhas de cabeçalho
    relevantes e dados a partir da quinta linha. A primeira linha útil do cabeçalho traz
    trimestres agrupados; a segunda traz níveis de instrução repetidos dentro de cada trimestre.
    """
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = list(csv.reader(fp, delimiter=";"))

    if len(reader) < 6:
        raise ValueError("CSV SIDRA não possui linhas suficientes para processar.")

    trimestre_header = reader[3]
    nivel_header = reader[4]
    data_rows = reader[5:]

    current_trimestre: str | None = None
    column_meta: dict[int, tuple[int, int, str]] = {}

    for idx in range(3, len(nivel_header)):
        tri_text = trimestre_header[idx].strip().strip('"') if idx < len(trimestre_header) else ""
        if tri_text:
            current_trimestre = tri_text

        nivel_text = nivel_header[idx].strip().strip('"')
        if not current_trimestre or nivel_text not in NIVEL_MAP:
            continue

        match = re.search(r"(\d+)º trimestre (\d{4})", current_trimestre)
        if not match:
            continue

        trimestre = int(match.group(1))
        ano = int(match.group(2))
        column_meta[idx] = (ano, trimestre, NIVEL_MAP[nivel_text])

    for raw in data_rows:
        if len(raw) < 4:
            continue
        nivel_geo = raw[0].strip().strip('"')
        if nivel_geo != "MU":
            continue

        cod = raw[1].strip().strip('"').zfill(7)
        nome = raw[2].strip().strip('"')

        for idx, (ano, trimestre, nivel_instrucao) in column_meta.items():
            value = raw[idx] if idx < len(raw) else None
            valor = to_float_or_none(value)
            rows.append(
                {
                    "codIBGE": cod,
                    "nomeSidra": nome,
                    "ano": ano,
                    "trimestre": trimestre,
                    "nivelInstrucao": nivel_instrucao,
                    "valorMilPessoas": valor,
                }
            )
    return rows


def transform_sidra() -> pd.DataFrame:
    # Agregação direta para evitar materializar ~2,2 milhões de linhas longas em memória.
    rows = normalize_sidra_rows(SIDRA_5919)
    agg: dict[tuple[str, str, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for item in rows:
        valor = item["valorMilPessoas"]
        if valor is None:
            continue
        key = (item["codIBGE"], item["nomeSidra"], item["ano"], item["nivelInstrucao"])
        agg[key][0] += float(valor)
        agg[key][1] += 1.0

    wide: dict[tuple[str, str, int], dict[str, Any]] = {}
    for (cod, nome, ano, nivel), (soma, count) in agg.items():
        base_key = (cod, nome, ano)
        if base_key not in wide:
            wide[base_key] = {"codIBGE": cod, "nomeSidra": nome, "ano": ano}
        wide[base_key][nivel] = soma / count if count else None

    records = list(wide.values())
    pivot = pd.DataFrame(records)

    for col in NIVEL_MAP.values():
        if col not in pivot.columns:
            pivot[col] = None

    def calc_pct(row: pd.Series) -> float | None:
        total = row.get("total")
        if total is None or pd.isna(total) or total == 0:
            return None
        medio_mais = 0.0
        for col in ["medioCompleto", "superiorIncompleto", "superiorCompleto"]:
            value = row.get(col)
            if value is not None and not pd.isna(value):
                medio_mais += float(value)
        return round((medio_mais / float(total)) * 100, 2)

    pivot["pctEnsinoMedioOuMais"] = pivot.apply(calc_pct, axis=1)
    pivot = pivot.rename(columns={"total": "populacaoTotal"})
    pivot.to_csv(SILVER_DIR / "sidra_anual.csv", index=False)
    return pivot

def flatten_municipio(item: dict[str, Any]) -> dict[str, Any]:
    # A maioria dos municípios traz a hierarquia em microrregião → mesorregião → UF.
    # Municípios mais recentes (ex.: Boa Esperança do Norte/MT) vêm com microrregião
    # nula e a UF acessível pela trilha regiao-imediata → regiao-intermediaria.
    micro = item.get("microrregiao") or {}
    uf = micro.get("mesorregiao", {}).get("UF")
    if not uf:
        imediata = item.get("regiao-imediata") or {}
        uf = imediata.get("regiao-intermediaria", {}).get("UF", {})
    regiao = uf.get("regiao", {})
    return {
        "codIBGE": str(item.get("id")).zfill(7),
        "nome": item.get("nome"),
        "codUF": uf.get("id"),
        "siglaUF": uf.get("sigla"),
        "nomeUF": uf.get("nome"),
        "codRegiao": regiao.get("id"),
        "siglaRegiao": regiao.get("sigla"),
        "nomeRegiao": regiao.get("nome"),
    }


def transform_localidades(sidra_df: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    if IBGE_MUNICIPIOS_JSON.exists():
        municipios = [flatten_municipio(item) for item in load_json(IBGE_MUNICIPIOS_JSON)]
        municipios_df = pd.DataFrame(municipios)
    else:
        if sidra_df is None:
            sidra_df = pd.read_csv(SILVER_DIR / "sidra_anual.csv", dtype={"codIBGE": str})
        municipios_df = sidra_df[["codIBGE", "nomeSidra"]].drop_duplicates().rename(columns={"nomeSidra": "nome"})
        municipios_df["codUF"] = municipios_df["codIBGE"].str[:2].astype(int)
        municipios_df["siglaUF"] = None
        municipios_df["nomeUF"] = None
        municipios_df["codRegiao"] = None
        municipios_df["siglaRegiao"] = None
        municipios_df["nomeRegiao"] = None

    if IBGE_ESTADOS_JSON.exists():
        estados_raw = load_json(IBGE_ESTADOS_JSON)
        ufs = [
            {
                "_id": item.get("id"),
                "sigla": item.get("sigla"),
                "nome": item.get("nome"),
                "regiaoId": item.get("regiao", {}).get("id"),
            }
            for item in estados_raw
        ]
        regioes_map = {
            item.get("regiao", {}).get("id"): {
                "_id": item.get("regiao", {}).get("id"),
                "sigla": item.get("regiao", {}).get("sigla"),
                "nome": item.get("regiao", {}).get("nome"),
            }
            for item in estados_raw
            if item.get("regiao")
        }
        regioes = list(regioes_map.values())
    else:
        ufs = []
        regioes = []

    municipios_df.to_csv(SILVER_DIR / "municipios_geo.csv", index=False)
    save_json(GOLD_DIR / "ufs.json", ufs)
    save_json(GOLD_DIR / "regioes.json", regioes)
    return municipios_df, ufs, regioes


def fontes_documentos() -> list[dict[str, Any]]:
    return [
        {
            "_id": FONTE_ATLAS_ID,
            "nome": "Atlas da Violência / Ipea / FBSP",
            "origem": "SIM / Datasus / Ministério da Saúde, elaboração Ipea/FBSP",
            "portal": "https://www.ipea.gov.br/atlasviolencia/",
            "licenca": "Uso acadêmico com citação obrigatória da fonte",
        },
        {
            "_id": FONTE_SIDRA_ID,
            "nome": "IBGE SIDRA - Tabela 5919",
            "origem": "PNAD Contínua / IBGE",
            "portal": "https://sidra.ibge.gov.br/tabela/5919",
            "licenca": "Dados abertos IBGE com citação obrigatória",
        },
        {
            "_id": FONTE_LOCALIDADES_ID,
            "nome": "IBGE API Localidades",
            "origem": "Catálogo territorial oficial do IBGE",
            "portal": "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
            "licenca": "Dados abertos IBGE com citação obrigatória",
        },
    ]


def build_municipio_documents(
    violencia: pd.DataFrame,
    sidra: pd.DataFrame,
    geo: pd.DataFrame,
) -> list[dict[str, Any]]:
    merged = violencia.merge(sidra, on=["codIBGE", "ano"], how="left")

    def calc_taxa(row: pd.Series) -> float | None:
        pop = row.get("populacaoTotal")
        if pop is None or pd.isna(pop) or float(pop) == 0:
            return None
        return round((float(row["homicidiosTotais"]) / float(pop)) * 100, 2)

    merged["taxaHomicidiosPor100k"] = merged.apply(calc_taxa, axis=1)

    geo = geo.drop_duplicates(subset=["codIBGE"])
    merged = merged.merge(geo, on="codIBGE", how="left")

    documentos: list[dict[str, Any]] = []
    for cod, group in merged.groupby("codIBGE"):
        group = group.sort_values("ano")
        first = group.iloc[0]
        # NaN é "truthy" em Python, então um simples `or` não cai no fallback quando
        # o município existe no Atlas mas não nas Localidades/SIDRA. Coalesce explícito.
        def _coalesce_nome(*candidatos: Any) -> str:
            for cand in candidatos:
                if cand is not None and not (isinstance(cand, float) and pd.isna(cand)):
                    texto = str(cand).strip()
                    if texto:
                        return texto
            return f"Município {cod}"

        nome = _coalesce_nome(first.get("nome"), first.get("nomeSidra"))

        series = []
        for _, row in group.iterrows():
            niveis = {
                "semInstrucao": round_or_none(row.get("semInstrucao")),
                "fundamentalIncompleto": round_or_none(row.get("fundamentalIncompleto")),
                "fundamentalCompleto": round_or_none(row.get("fundamentalCompleto")),
                "medioIncompleto": round_or_none(row.get("medioIncompleto")),
                "medioCompleto": round_or_none(row.get("medioCompleto")),
                "superiorIncompleto": round_or_none(row.get("superiorIncompleto")),
                "superiorCompleto": round_or_none(row.get("superiorCompleto")),
                "naoDeterminado": round_or_none(row.get("naoDeterminado")),
            }
            niveis = {k: v for k, v in niveis.items() if v is not None}

            fonte_ids = [FONTE_ATLAS_ID]
            if row.get("populacaoTotal") is not None and not pd.isna(row.get("populacaoTotal")):
                fonte_ids.append(FONTE_SIDRA_ID)

            serie = {
                "ano": int(row["ano"]),
                "homicidiosHomens": int(row["homicidiosHomens"]),
                "homicidiosMulheres": int(row["homicidiosMulheres"]),
                "homicidiosTotais": int(row["homicidiosTotais"]),
                "fonteIds": fonte_ids,
            }
            optional_fields = {
                "populacaoTotal": round_or_none(row.get("populacaoTotal")),
                "taxaHomicidiosPor100k": round_or_none(row.get("taxaHomicidiosPor100k")),
                "pctEnsinoMedioOuMais": round_or_none(row.get("pctEnsinoMedioOuMais")),
            }
            serie.update({k: v for k, v in optional_fields.items() if v is not None})
            if niveis:
                serie["niveisInstrucao"] = niveis
            series.append(serie)

        doc = {
            "codIBGE": int(cod),
            "codIBGEStr": cod,
            "nome": nome,
            "codUF": int(first["codUF"]) if first.get("codUF") is not None and not pd.isna(first.get("codUF")) else None,
            "siglaUF": first.get("siglaUF") if not pd.isna(first.get("siglaUF")) else None,
            "nomeUF": first.get("nomeUF") if not pd.isna(first.get("nomeUF")) else None,
            "codRegiao": int(first["codRegiao"]) if first.get("codRegiao") is not None and not pd.isna(first.get("codRegiao")) else None,
            "siglaRegiao": first.get("siglaRegiao") if not pd.isna(first.get("siglaRegiao")) else None,
            "nomeRegiao": first.get("nomeRegiao") if not pd.isna(first.get("nomeRegiao")) else None,
            "seriesAnuais": series,
            "schemaVersion": 1,
        }
        doc = {k: v for k, v in doc.items() if v is not None}
        documentos.append(doc)

    return documentos


def run_transform(ano_min: int | None = None, ano_max: int | None = None) -> None:
    ensure_dirs(SILVER_DIR, GOLD_DIR)
    violencia = transform_violencia()
    sidra = transform_sidra()
    geo, _, _ = transform_localidades(sidra)

    # Recorte opcional por intervalo de anos (exercício inicial/final). Filtramos as
    # camadas Silver antes da modelagem para que apenas as séries dentro de [min, max]
    # cheguem ao Gold; municípios sem nenhuma série no intervalo são naturalmente
    # descartados em build_municipio_documents (groupby sobre violencia já recortada).
    if ano_min is not None:
        violencia = violencia[violencia["ano"] >= ano_min]
        sidra = sidra[sidra["ano"] >= ano_min]
    if ano_max is not None:
        violencia = violencia[violencia["ano"] <= ano_max]
        sidra = sidra[sidra["ano"] <= ano_max]

    documentos = build_municipio_documents(violencia, sidra, geo)
    save_json(GOLD_DIR / "municipios.json", documentos)
    save_json(GOLD_DIR / "fontes.json", fontes_documentos())
    print(f"Documentos de municípios gerados: {len(documentos)}")
    print(f"Arquivo Gold: {GOLD_DIR / 'municipios.json'}")
