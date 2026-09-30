"""Data wrangling: CSV / JSON tools over workspace files."""
from __future__ import annotations

import csv
import json
import re
import statistics

from .builtin_fmt import fmt
from .helpers import Ctx, read_text
from .registry import ToolError


def load_csv(ctx: Ctx, path: str) -> tuple[list[str], list[dict[str, str]]]:
    text = read_text(ctx.in_ws(str(path)), 2_000_000)
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ToolError("empty csv")
    return list(rows[0].keys()), rows


def col(rows: list[dict[str, str]], column: str) -> list[str]:
    if column not in rows[0]:
        raise ToolError(f"no column '{column}'; columns: {', '.join(rows[0])}")
    return [r[column] for r in rows]


def nums(values: list[str]) -> list[float]:
    out = []
    for v in values:
        try:
            out.append(float(v.replace(",", "")))
        except ValueError:
            pass
    return out


def json_path(obj, query: str):
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", query):
        try:
            obj = obj[int(part[1:-1])] if part.startswith("[") else obj[part]
        except (KeyError, IndexError, TypeError):
            raise ToolError(f"path not found at '{part}'")
    return obj


def install(ctx: Ctx) -> None:
    reg = ctx.reg

    @reg.register("csv_head", "show the columns and first rows of a CSV file", {"path": "relative csv path", "n": "rows"}, feature="data_wrangling", optional=("n",))
    def csv_head(path: str, n: str = "3") -> str:
        cols, rows = load_csv(ctx, path)
        return f"{len(rows)} rows; columns: {', '.join(cols)}; first: " + " | ".join(",".join(r.values()) for r in rows[: int(n)])

    @reg.register("csv_stats", "count, min, max, mean, median of a numeric CSV column (statistics, average)", {"path": "relative csv path", "column": "column name"}, feature="data_wrangling")
    def csv_stats(path: str, column: str) -> str:
        _, rows = load_csv(ctx, path)
        v = nums(col(rows, column))
        if not v:
            raise ToolError(f"column '{column}' has no numbers")
        sd = statistics.stdev(v) if len(v) > 1 else 0
        return f"count={len(v)} min={fmt(min(v))} max={fmt(max(v))} mean={fmt(statistics.mean(v))} median={fmt(statistics.median(v))} stdev={fmt(sd)} sum={fmt(sum(v))}"

    @reg.register("csv_filter", "count and preview rows where a column matches (filter rows)", {"path": "relative csv path", "column": "column", "op": "= != > < >= <= contains", "value": "value"}, feature="data_wrangling")
    def csv_filter(path: str, column: str, op: str, value: str) -> str:
        _, rows = load_csv(ctx, path)
        col(rows, column)

        if op not in ("=", "!=", ">", "<", ">=", "<=", "contains"):
            raise ToolError("op must be one of = != > < >= <= contains")

        def keep(r: dict[str, str]) -> bool:
            a = r[column]
            if op == "contains":
                return str(value).lower() in a.lower()
            try:
                x, y = float(a), float(value)
            except ValueError:  # text compare for = / !=; rows that aren't numbers never match numeric ops
                return (a == str(value)) if op == "=" else (a != str(value)) if op == "!=" else False
            return {"=": x == y, "!=": x != y, ">": x > y, "<": x < y, ">=": x >= y, "<=": x <= y}[op]

        hit = [r for r in rows if keep(r)]
        return f"{len(hit)} of {len(rows)} rows match; first: " + " | ".join(",".join(r.values()) for r in hit[:3])

    @reg.register("csv_group", "count rows per value of a column, optionally summing another (group by, pivot)", {"path": "relative csv path", "column": "group column", "sum_column": "optional numeric column"}, feature="data_wrangling", optional=("sum_column",))
    def csv_group(path: str, column: str, sum_column: str = "") -> str:
        _, rows = load_csv(ctx, path)
        col(rows, column)
        if sum_column:
            col(rows, sum_column)
            sums: dict[str, float] = {}
            for r in rows:
                sums[r[column]] = sums.get(r[column], 0) + sum(nums([r[sum_column]]))
            return "; ".join(f"{k}: {fmt(v)}" for k, v in sorted(sums.items(), key=lambda kv: -kv[1])[:15])
        counts: dict[str, int] = {}
        for r in rows:
            counts[r[column]] = counts.get(r[column], 0) + 1
        return "; ".join(f"{k}: {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])[:15])

    @reg.register("json_query", "read a value from a JSON file by path like a.b[0].c", {"path": "relative json path", "query": "dotted path"}, feature="data_wrangling")
    def json_query(path: str, query: str) -> str:
        obj = json.loads(read_text(ctx.in_ws(str(path)), 2_000_000))
        val = json_path(obj, str(query)) if str(query).strip() not in ("", ".") else obj
        return json.dumps(val)[:1000]
