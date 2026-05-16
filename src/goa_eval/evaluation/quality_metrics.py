def finite_metric_values(results, symbol):
    values = []
    for result in results:
        if result.symbol == symbol and isinstance(result.value, (float, int)):
            values.append(float(result.value))
    return values
