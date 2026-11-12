"""Exact deterministic distribution of integer minor currency units."""


def divide_money(total, weights):
    if not weights:
        return []
    divisor = sum(weights)
    weights = weights if divisor else [1] * len(weights)
    divisor = sum(weights)
    portions = [total * weight // divisor for weight in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % divisor), i))
    for index in order[: total - sum(portions)]:
        portions[index] += 1
    return portions
