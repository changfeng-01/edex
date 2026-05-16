def summarize_hard_checks(results):
    collected = {}
    for result in results:
        if result.metric_type.startswith("hard"):
            collected.setdefault(result.version_name, {}).setdefault(result.symbol, []).append(result.passed)
    return {
        version: {symbol: all(value is True for value in values) for symbol, values in checks.items()}
        for version, checks in collected.items()
    }
