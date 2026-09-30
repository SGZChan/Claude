"""Calculator extras (units, dates) and small utilities."""
from __future__ import annotations

import math
import re
import secrets
from datetime import date, datetime, timedelta

from .builtin_fmt import fmt
from .helpers import Ctx
from .registry import ToolError

UNITS: dict[str, dict[str, float]] = {
    "length": {"mm": .001, "cm": .01, "m": 1, "km": 1000, "in": .0254, "inch": .0254, "ft": .3048, "feet": .3048, "yd": .9144, "mi": 1609.344, "mile": 1609.344, "miles": 1609.344},
    "mass": {"mg": .001, "g": 1, "kg": 1000, "oz": 28.3495, "lb": 453.592, "lbs": 453.592},
    "volume": {"ml": .001, "l": 1, "liter": 1, "gal": 3.78541, "cup": .236588, "floz": .0295735},
    "time": {"s": 1, "sec": 1, "min": 60, "h": 3600, "hour": 3600, "hours": 3600, "day": 86400, "days": 86400, "week": 604800},
    "data": {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3},
}
TEMPS = {"c", "f", "k"}
WORDS = ("amber anchor apple arrow aspen atlas badge basil beach berry birch blade bloom bolt brave breeze bridge brook cabin candle canyon cedar "
         "chalk cherry cliff cloud clover cobalt comet coral crane creek crown dawn delta dune eagle ember fable falcon fern field flint forest frost garnet "
         "glade glow granite harbor hazel heron hill honey iris island ivory jade jasper juniper kettle lake lantern larch lemon lilac linen lotus maple "
         "marble meadow mist moon moss nectar oak ocean olive onyx orchid otter pearl pebble pine plum pond quartz quill raven reef ridge river robin "
         "sage sand shell silver slate snow spruce star stone storm summit swan thistle thunder tide timber topaz tulip valley velvet violet willow wren zephyr").split()


def to_kelvin(v: float, u: str) -> float:
    return v + 273.15 if u == "c" else (v - 32) * 5 / 9 + 273.15 if u == "f" else v


def from_kelvin(k: float, u: str) -> float:
    return k - 273.15 if u == "c" else (k - 273.15) * 9 / 5 + 32 if u == "f" else k


def convert(value: float, a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    if a in TEMPS and b in TEMPS:
        return from_kelvin(to_kelvin(value, a), b)
    for table in UNITS.values():
        if a in table and b in table:
            return value * table[a] / table[b]
    raise ToolError(f"cannot convert '{a}' to '{b}'")


def parse_date(s: str) -> date:
    s = str(s).strip().lower()
    if s == "today":
        return date.today()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise ToolError("dates must be YYYY-MM-DD or 'today'")


def install(ctx: Ctx) -> None:
    reg = ctx.reg

    @reg.register("unit_convert", "convert between units: length, mass, volume, temperature, time, data (miles to km, kg to lb)", {"value": "number", "from_unit": "unit", "to_unit": "unit"}, feature="calculator")
    def unit_convert(value: str, from_unit: str, to_unit: str) -> str:
        try:
            v = float(value)
        except ValueError:
            raise ToolError("value must be a number")
        return f"{convert(v, from_unit, to_unit):.6f}".rstrip("0").rstrip(".") + f" {to_unit}"

    @reg.register("date_math", "add or subtract days from a date (YYYY-MM-DD or today)", {"start": "date", "days": "days, may be negative"}, feature="calculator")
    def date_math(start: str, days: str) -> str:
        d = parse_date(start) + timedelta(days=int(days))
        return f"{d.isoformat()} ({d.strftime('%A')})"

    @reg.register("date_diff", "number of days between two dates", {"a": "date", "b": "date"}, feature="calculator")
    def date_diff(a: str, b: str) -> str:
        return f"{(parse_date(b) - parse_date(a)).days} days"

    @reg.register("password_gen", "generate a strong random password", {"length": "characters"}, feature="utilities", optional=("length",))
    def password_gen(length: str = "16") -> str:
        n = max(8, min(int(length), 64))
        alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*-_"
        return "".join(secrets.choice(alphabet) for _ in range(n))

    @reg.register("passphrase", "generate a memorable random passphrase", {"words": "how many words"}, feature="utilities", optional=("words",))
    def passphrase(words: str = "4") -> str:
        n = max(3, min(int(words), 10))
        bits = round(n * math.log2(len(WORDS)))
        return "-".join(secrets.choice(WORDS) for _ in range(n)) + f" (~{bits} bits)"

    @reg.register("text_stats", "word count, sentence count and reading time of some text", {"text": "text"}, feature="utilities")
    def text_stats(text: str) -> str:
        w = len(str(text).split())
        s = len(re.findall(r"[.!?]+(?:\s|$)", str(text))) or (1 if w else 0)
        return f"{w} words, {s} sentences, {len(str(text))} chars, ~{max(1, round(w / 200))} min read"
