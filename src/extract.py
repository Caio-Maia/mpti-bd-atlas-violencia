from __future__ import annotations

import shutil
import requests
from pathlib import Path

from config import (
    ATLAS_HOMENS,
    ATLAS_MULHERES,
    SIDRA_5919,
    IBGE_MUNICIPIOS_JSON,
    IBGE_ESTADOS_JSON,
    BRONZE_DIR,
)
from utils import ensure_dirs, save_json

IBGE_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
IBGE_ESTADOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"


def copy_if_provided(source: str | None, target: Path) -> None:
    if source:
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {src}")
        shutil.copyfile(src, target)


def extract_local_files(
    homens_csv: str | None = None,
    mulheres_csv: str | None = None,
    sidra_csv: str | None = None,
) -> None:
    """Copia arquivos locais para a camada Bronze, preservando os dados brutos."""
    ensure_dirs(BRONZE_DIR)
    copy_if_provided(homens_csv, ATLAS_HOMENS)
    copy_if_provided(mulheres_csv, ATLAS_MULHERES)
    copy_if_provided(sidra_csv, SIDRA_5919)

    for required in [ATLAS_HOMENS, ATLAS_MULHERES, SIDRA_5919]:
        if not required.exists():
            raise FileNotFoundError(
                f"Arquivo Bronze obrigatório não encontrado: {required}. "
                "Informe o caminho com os argumentos --homens, --mulheres e --sidra."
            )


def fetch_json(url: str) -> list[dict]:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def extract_ibge_localidades(force: bool = False) -> None:
    """Coleta JSON da API Localidades do IBGE para a camada Bronze."""
    ensure_dirs(BRONZE_DIR)

    if force or not IBGE_MUNICIPIOS_JSON.exists():
        municipios = fetch_json(IBGE_MUNICIPIOS_URL)
        save_json(IBGE_MUNICIPIOS_JSON, municipios)

    if force or not IBGE_ESTADOS_JSON.exists():
        estados = fetch_json(IBGE_ESTADOS_URL)
        save_json(IBGE_ESTADOS_JSON, estados)


def run_extract(
    homens_csv: str | None = None,
    mulheres_csv: str | None = None,
    sidra_csv: str | None = None,
    force_api: bool = False,
    skip_api: bool = False,
) -> None:
    extract_local_files(homens_csv, mulheres_csv, sidra_csv)
    if not skip_api:
        extract_ibge_localidades(force=force_api)
