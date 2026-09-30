def fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(round(x, 4))
