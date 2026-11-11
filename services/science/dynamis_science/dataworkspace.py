"""Read-only access to admitted Parquet tables for the native Data Workspace (RES-636).

Everything here is a lazy Polars query over Parquet files: paginated, filtered and sorted without loading a
table, with column names validated against the schema and no way to write, attach or read other files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

MAX_PAGE = 1000
MAX_QUERY_ROWS = 10_000
OPS = ("contains", "=", "!=", "<", "<=", ">", ">=", "is empty", "is not empty")
UNIT_SUFFIXES = (("_n_s_kg", "N·s/kg"), ("_w_kg", "W/kg"), ("_hz", "Hz"), ("_kg", "kg"), ("_cm", "cm"), ("_ms", "ms"),
                 ("_m", "m"), ("_s", "s"), ("_n", "N"))
_FORBIDDEN = re.compile(
    r"\b(read_\w+|scan_\w+|copy|attach|install|load|pragma|create|insert|update|delete|drop|alter|export|set|call|"
    r"truncate|merge|replace|grant|execute|explain|show|use|describe)\b|;|--|/\*|['\"][^'\"]*[\\/.][^'\"]*['\"]", re.I)


def unit_of(column: str) -> str:
    """Unit from the canonical column-name suffix (admitted tables are normalized to these units)."""
    return next((unit for suffix, unit in UNIT_SUFFIXES if column.endswith(suffix)), "")


def profile(path: Path) -> dict[str, Any]:
    lazy = pl.scan_parquet(path)
    schema = lazy.collect_schema()
    aggs: list[pl.Expr] = [pl.len().alias("__rows")]
    for name, dtype in schema.items():
        missing = pl.col(name).is_null()
        if dtype.is_float():
            missing = missing | pl.col(name).is_nan()
        aggs.append(missing.sum().alias(f"{name}\0m"))
        if dtype.is_numeric():
            aggs += [pl.col(name).min().alias(f"{name}\0lo"), pl.col(name).max().alias(f"{name}\0hi")]
    row = lazy.select(aggs).collect().row(0, named=True)
    rows = row["__rows"]
    columns = []
    for name, dtype in schema.items():
        missing = int(row[f"{name}\0m"])
        columns.append({"name": name, "dtype": str(dtype), "unit": unit_of(name), "missing": missing,
                        "missing_pct": (100.0 * missing / rows) if rows else 0.0,
                        "min": row.get(f"{name}\0lo"), "max": row.get(f"{name}\0hi")})
    return {"rows": rows, "columns": columns}


def _condition(schema: pl.Schema, flt: dict[str, Any]) -> pl.Expr:
    column, op, value = flt["column"], flt["op"], flt.get("value", "")
    if column not in schema:
        raise ValueError(f"Unknown column {column}.")
    if op not in OPS:
        raise ValueError(f"Unsupported filter {op}.")
    col = pl.col(column)
    if op == "is empty":
        return col.is_null()
    if op == "is not empty":
        return col.is_not_null()
    dtype = schema[column]
    if op == "contains":
        return col.cast(pl.Utf8).str.to_lowercase().str.contains(re.escape(str(value).lower())).fill_null(False)
    if dtype.is_numeric():
            aggs += [pl.col(name).min().alias(f"{name}\0lo"), pl.col(name).max().alias(f"{name}\0hi")]
    row = lazy.select(aggs).collect().row(0, named=True)
    rows = row["__rows"]
    columns = []
    for name, dtype in schema.items():
        missing = int(row[f"{name}\0m"])
        columns.append({"name": name, "dtype": str(dtype), "unit": unit_of(name), "missing": missing,
                        "missing_pct": (100.0 * missing / rows) if rows else 0.0,
                        "min": row.get(f"{name}\0lo"), "max": row.get(f"{name}\0hi")})
    return {"rows": rows, "columns": columns}


def _condition(schema: pl.Schema, flt: dict[str, Any]) -> pl.Expr:
    column, op, value = flt["column"], flt["op"], flt.get("value", "")
    if column not in schema:
        raise ValueError(f"Unknown column {column}.")
    if op not in OPS:
        raise ValueError(f"Unsupported filter {op}.")
    col = pl.col(column)
    if op == "is empty":
        return col.is_null()
    if op == "is not empty":
        return col.is_not_null()
    dtype = schema[column]
    if op == "contains":
        return col.cast(pl.Utf8).str.contains(re.escape(str(value)), literal=False).fill_null(False) if False else \
            col.cast(pl.Utf8).str.to_lowercase().str.contains(re.escape(str(value).lower())).fill_null(False)
    if dtype.is_numeric():
        try:
            number = float(value)
        except ValueError as error:
            raise ValueError(f"'{value}' is not a number for {column}.") from error
        target = pl.lit(number)
    else:
        target = pl.lit(str(value))
        col = col.cast(pl.Utf8)
    return {"=": col == target, "!=": col != target, "<": col < target, "<=": col <= target,
            ">": col > target, ">=": col >= target}[op].fill_null(False)


def page(path: Path, offset: int = 0, limit: int = 200, filters: list[dict[str, Any]] | None = None,
         sort: str | None = None, descending: bool = False, columns: list[str] | None = None) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= MAX_PAGE:
        raise ValueError(f"offset must be non-negative and limit between 1 and {MAX_PAGE}.")
    lazy = pl.scan_parquet(path)
    schema = lazy.collect_schema()
    for flt in filters or []:
        lazy = lazy.filter(_condition(schema, flt))
    total = int(lazy.select(pl.len()).collect().item())
    if sort:
        if sort not in schema:
            raise ValueError(f"Unknown column {sort}.")
        lazy = lazy.sort(sort, descending=descending, nulls_last=True, maintain_order=True)
    chosen = [c for c in (columns or list(schema)) if c in schema]
    if not chosen:
        raise ValueError("Select at least one column.")
    frame = lazy.select(chosen).slice(offset, limit).collect()
    return {"columns": chosen, "rows": frame.rows(), "total_rows": total, "offset": offset, "limit": limit}


def query(tables: dict[str, Path], sql: str, limit: int = 1000) -> dict[str, Any]:
    """Bounded read-only SELECT over the snapshot's tables (Polars SQL; no files, no writes)."""
    text = sql.strip()
    if not 1 <= limit <= MAX_QUERY_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")
    if not re.match(r"(select|with)\b", text, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if _FORBIDDEN.search(text):
        raise ValueError("The query uses a statement, function or path that is not allowed in the read-only workspace.")
    context = pl.SQLContext({name: pl.scan_parquet(path) for name, path in tables.items()})
    try:
        frame = context.execute(text, eager=False).head(limit + 1).collect()
    except Exception as error:
        raise ValueError(f"Query failed: {str(error).splitlines()[0][:300]}") from error
    return {"columns": frame.columns, "rows": frame.head(limit).rows(), "truncated": frame.height > limit, "limit": limit}
