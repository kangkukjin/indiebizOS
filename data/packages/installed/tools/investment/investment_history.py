"""주가 이력 행 계약 — 공급자와 무관하게 표본 추출 전 적용한다."""


def normalize_history(prices):
    """오래된 순서의 일봉에 공통 열과 전일 종가 대비 등락을 채운다.

    첫 행의 전일은 조회 범위 밖이므로 추측하지 않는다. vwap 등 공급자가
    제공하지 않은 값은 null로 남기고, 표본 사이의 차이를 일일 등락으로 만들지 않는다.
    """
    previous = None
    for row in prices:
        for field in ("date", "open", "high", "low", "close", "volume", "vwap"):
            row.setdefault(field, None)
        close = row["close"]
        if previous and close is not None:
            row["change"] = round(close - previous, 4)
            row["change_percent"] = round((close - previous) / previous * 100, 2)
        else:
            row["change"] = None
            row["change_percent"] = None
        if close is not None:
            previous = close
    return prices
