from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, data: Any, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False garante que NaN/Infinity nunca virem JSON inválido e cheguem
    # ao Mongo como double NaN (que furaria $avg e os filtros `$ne: null`).
    with path.open("w", encoding="utf-8") as fp:
        if pretty:
            json.dump(data, fp, ensure_ascii=False, indent=2, allow_nan=False)
        else:
            json.dump(data, fp, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def only_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def to_int_or_none(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return None


def to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("\ufeff", "")
    if text in {"", "...", "..", "-", "X", "x"}:
        return None
    text = text.replace(".", ".").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def round_or_none(value: float | None, ndigits: int = 2) -> float | None:
    if value is None:
        return None
    number = float(value)
    # NaN/inf não são None mas também não são valores válidos: precisam virar None
    # aqui, senão escapam do filtro `if v is not None` e poluem médias ($avg → NaN).
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return round(number, ndigits)
