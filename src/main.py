from __future__ import annotations

import argparse

from extract import run_extract
from transform import run_transform
from load import run_load


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline ETL MPTIBD - Atlas da Violência x SIDRA")
    parser.add_argument("--homens", help="Caminho do CSV Atlas Homicídios Homens")
    parser.add_argument("--mulheres", help="Caminho do CSV Atlas Homicídios Mulheres")
    parser.add_argument("--sidra", help="Caminho do CSV SIDRA Tabela 5919")
    parser.add_argument("--skip-api", action="store_true", help="Não baixar API Localidades; usa fallback parcial")
    parser.add_argument("--force-api", action="store_true", help="Baixar novamente os JSONs do IBGE")
    parser.add_argument("--drop-db", action="store_true", help="Apagar banco antes da carga")
    parser.add_argument("--ano-min", type=int, default=None, help="Ano inicial do recorte (inclusive)")
    parser.add_argument("--ano-max", type=int, default=None, help="Ano final do recorte (inclusive)")
    parser.add_argument("--only", choices=["extract", "transform", "load", "all"], default="all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.only in {"extract", "all"}:
        run_extract(args.homens, args.mulheres, args.sidra, args.force_api, args.skip_api)
    if args.only in {"transform", "all"}:
        run_transform(args.ano_min, args.ano_max)
    if args.only in {"load", "all"}:
        run_load(drop_database=args.drop_db)


if __name__ == "__main__":
    main()
