# -*- coding: utf-8 -*-
"""Shared normalization rules for market-review region values."""

from typing import Optional


MARKET_REVIEW_REGION_ORDER = ("cn", "hk", "us", "jp", "kr")
MARKET_REVIEW_REGION_SET = frozenset(MARKET_REVIEW_REGION_ORDER)
MARKET_REVIEW_REGION_ALL = ",".join(MARKET_REVIEW_REGION_ORDER)
MARKET_REVIEW_REGION_VALID_INPUTS = (*MARKET_REVIEW_REGION_ORDER, "both")


def normalize_market_review_region_lenient(value: Optional[str]) -> Optional[str]:
    """Normalize persistent config input while preserving legacy filtering.

    ``None`` and an empty string retain the historical ``cn`` default. Comma
    lists keep only supported markets, and ``both`` expands to every market.
    ``None`` is returned only when a non-defaultable value has no valid token.
    """

    normalized = str(value or "cn").strip().lower()
    if normalized in MARKET_REVIEW_REGION_SET:
        return normalized
    if normalized == "both":
        return MARKET_REVIEW_REGION_ALL

    if "," in normalized:
        requested = {token.strip() for token in normalized.split(",") if token.strip()}
        if "both" in requested:
            return MARKET_REVIEW_REGION_ALL
        regions = [region for region in MARKET_REVIEW_REGION_ORDER if region in requested]
        if regions:
            return ",".join(regions)

    return None


def normalize_market_review_region_strict(value: str) -> str:
    """Validate and canonicalize a request-scoped market-review region.

    Unlike persistent configuration parsing, request input is fail-fast: empty
    values, empty tokens, unknown tokens, and mixing ``both`` with other tokens
    raise ``ValueError`` instead of being filtered or defaulted.
    """

    normalized = value.strip().lower()
    valid_hint = (
        f"{', '.join(MARKET_REVIEW_REGION_VALID_INPUTS)}，"
        "또는 cn/hk/us/jp/kr 를 쉼표로 구분한 올바른 조합"
    )
    if not normalized:
        raise ValueError(f"region 은 비워둘 수 없습니다. 허용 값: {valid_hint}")

    tokens = [token.strip() for token in normalized.split(",")]
    if any(not token for token in tokens):
        raise ValueError(f"region 에 빈 항목이 있으면 안 됩니다. 허용 값: {valid_hint}")

    invalid_tokens = sorted({token for token in tokens if token not in MARKET_REVIEW_REGION_SET and token != "both"})
    if invalid_tokens:
        raise ValueError(
            f"region 에 잘못된 값이 있습니다: {', '.join(invalid_tokens)}. 허용 값: {valid_hint}"
        )

    if "both" in tokens:
        if len(tokens) != 1:
            raise ValueError("region 의 both 는 단독으로만 쓸 수 있고 다른 시장과 섞을 수 없습니다")
        return MARKET_REVIEW_REGION_ALL

    requested = set(tokens)
    return ",".join(region for region in MARKET_REVIEW_REGION_ORDER if region in requested)
