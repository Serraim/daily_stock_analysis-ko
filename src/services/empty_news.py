# -*- coding: utf-8 -*-
"""뉴스 검색을 하지 않았거나 결과가 0건일 때 리포트에 넣는 안내 문구.

단일 기준: 문자열 조합 렌더러(src/notification.py)와 템플릿 렌더링 경로
(src/services/report_renderer.py + templates/*.j2)가 이 모듈을 함께 써서,
같은 분석 결과를 어떤 채널에서는 알리고 다른 채널에서는 침묵하는 일을 막는다.

안내가 말하는 것은 "이번 결론에 뉴스 근거를 썼는가"이므로, 첫 번째 기준은 분석이 실제로 받은 뉴스
근거(news_context)가 비어 있지 않은지이지, 검색이 몇 건 걸렸는지가 아니다. news_context는 실시간 검색,
소셜 심리, 또는 로컬에 저장된 뉴스 풀에서 올 수 있고, 뒤의 둘은 모델 입력에 들어가도 검색 건수를 만들지 않는다. 건수만 보면
이런 분석을 "뉴스 근거 미포함"으로 잘못 보고한다(review OR-COR-2e4b9d61).

그래서 news_result_count는 두 번째 기준으로 물러나, "정말 근거가 없을 때" 그 이유를 설명하는 데만 쓴다:
    None  검색 안 함(검색 채널 미설정)
    0     검색했지만 0건(요청 제한, 모두 실패 등)
    > 0   실시간 검색 결과 있음(이때는 근거가 반드시 있음)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional, Tuple

from src.report_language import SUPPORTED_REPORT_LANGUAGES

_ZH_NOT_CONFIGURED = "⚠️ 未配置搜索渠道，本次分析未纳入新闻面证据。"
_EN_NOT_CONFIGURED = (
    "⚠️ No news search channel is configured; "
    "this analysis does not incorporate news-based evidence."
)
_ZH_ZERO_RESULTS = "⚠️ 本次未获取到可用的新闻面数据，以下结论未纳入新闻维度证据。"
_EN_ZERO_RESULTS = (
    "⚠️ No news data could be retrieved for this run; "
    "the conclusions below do not incorporate news-based evidence."
)
_KO_NOT_CONFIGURED = (
    "⚠️ 뉴스 검색 채널이 설정되지 않아 이번 분석에는 "
    "뉴스 근거를 반영하지 않았습니다."
)
_KO_ZERO_RESULTS = (
    "⚠️ 이번 분석에서 사용 가능한 뉴스 데이터를 가져오지 못해 "
    "아래 결론에는 뉴스 근거를 반영하지 않았습니다."
)

_DISCLOSURES = {
    "zh": (_ZH_NOT_CONFIGURED, _ZH_ZERO_RESULTS),
    "en": (_EN_NOT_CONFIGURED, _EN_ZERO_RESULTS),
    "ko": (_KO_NOT_CONFIGURED, _KO_ZERO_RESULTS),
}

if set(_DISCLOSURES) != set(SUPPORTED_REPORT_LANGUAGES):
    raise RuntimeError(
        "Empty-news disclosures must cover every SUPPORTED_REPORT_LANGUAGES value"
    )


def persisted_news_result_state(
    raw_result: Any,
    context_snapshot: Any = None,
) -> Tuple[Optional[int], bool]:
    """저장된 데이터에서 건수와 그 신뢰도를 복원한다.

    새 기록은 raw_result에 세 가지 상태 값을 분명히 저장한다. 예전 기록은 context_snapshot에
    0 / >0 건수를 남겼을 수 있다. 두 곳 모두 필드가 없으면 legacy unknown으로만 판단할 수 있고, 필드가 없는 것을
    명확한 None으로 취급하면 안 된다.
    """
    if isinstance(raw_result, Mapping):
        if raw_result.get("news_result_count_known") is False:
            return None, False
        if "news_result_count" in raw_result:
            return raw_result.get("news_result_count"), True

    if isinstance(context_snapshot, Mapping) and "news_result_count" in context_snapshot:
        return context_snapshot.get("news_result_count"), True

    return None, False


def news_evidence_present(*sources: Any) -> bool:
    """이번 분석이 정말 뉴스 근거를 받았는지. 출처 중 하나라도 참이면 참이다.

    각 출처는 실제 건수(int)이거나 **자리표시 문구를 뺀** 내용 문자열이다.
    실시간 검색, 소셜 심리, 로컬 뉴스 풀을 각각 한 경로로 치며, pipeline의 두 경로 모두 이 함수를 쓴다.
    다른 곳에서 따로 판단을 만들지 말 것.

    **pipeline이 합쳐 놓은 news_context 전체를 넘기지 말 것.**
    `src/search_service.py`의 `format_intel_report()`는 0건이어도
    `【XX 情报搜索结果】` 제목과 항목별 "未找到相关信息" 자리표시 문구를 출력하므로 전체 문자열은 항상
    비어 있지 않다. 이것으로 판단하면 "검색했지만 하나도 못 얻음"이 "근거 있음"으로 바뀌어, 이 모듈이 채우려는
    안내를 정확히 삼켜 버린다(review OR-COR-8f4c2d1b). 판단은 출처별로 하나씩 등록해서 해야지 문자열 냄새로 하면 안 된다.
    """
    for source in sources:
        if source is None or isinstance(source, bool):
            if source:
                return True
            continue
        if isinstance(source, (int, float)):
            if source > 0:
                return True
            continue
        if str(source).strip():
            return True
    return False


def _disclosure_for_state(
    news_result_count: Optional[int],
    *,
    known: bool,
    evidence_present: bool,
    language: str,
) -> Optional[str]:
    try:
        not_configured, zero_results = _DISCLOSURES[language]
    except KeyError as exc:
        raise ValueError(f"Unsupported report language for empty-news disclosure: {language}") from exc

    if not known:
        return None
    # 근거가 있으면 어느 출처에서 왔든 안내하지 않는다. 건수는 "근거 없음"의 이유만 설명한다.
    if evidence_present:
        return None
    if news_result_count is None:
        return not_configured
    if news_result_count == 0:
        return zero_results
    return None


def empty_news_disclosure(result: Any, language: str = "zh") -> Optional[str]:
    """검색을 안 했거나 0건이면 해당 안내를 돌려주고, 정상적으로 결과가 있으면 None을 돌려준다.

    판단은 모델이 뉴스 관련 문장을 만들었는지와 무관해야 한다: analyzer 출력 schema는
    뉴스가 없어도 market_sentiment / hot_topics를 채우라고 요구하므로, 이 필드들이
    비었는지로 정하면 "모델이 만든 심리 판단은 보여 주면서 뉴스 근거 없음은 숨기는"
    최악의 조합이 생긴다.
    """
    if isinstance(result, Mapping):
        news_result_count, known = persisted_news_result_state(result)
        evidence_present = persisted_news_evidence_present(result, news_result_count)
    else:
        news_result_count = getattr(result, "news_result_count", None)
        known = getattr(result, "news_result_count_known", True)
        evidence_present = bool(getattr(result, "news_evidence_present", False))
    return _disclosure_for_state(
        news_result_count,
        known=known,
        evidence_present=evidence_present,
        language=language,
    )


def empty_news_disclosure_from_stored(
    raw_result: Any,
    context_snapshot: Any,
    language: str = "zh",
) -> Optional[str]:
    """기록/API 진입점용으로 저장된 데이터에서 안내를 만든다. 예전 기록에 필드가 없으면 조용히 넘어간다."""
    news_result_count, known = persisted_news_result_state(raw_result, context_snapshot)
    return _disclosure_for_state(
        news_result_count,
        known=known,
        evidence_present=persisted_news_evidence_present(raw_result, news_result_count),
        language=language,
    )


def persisted_news_evidence_present(raw_result: Any, news_result_count: Optional[int]) -> bool:
    """저장된 데이터에서 "이번 분석이 뉴스 근거를 썼는지"를 복원한다.

    이 PR 이전에 기록된 데이터에는 이 필드가 없으므로 건수로 추정한다: >0이면 근거가 있었던 것이고,
    나머지는 근거 없음으로 처리한다. 그 기록의 당시 리포트 모습과 같으므로 예전 리포트를 소급해 바꾸지 않는다.
    """
    if isinstance(raw_result, Mapping) and "news_evidence_present" in raw_result:
        return bool(raw_result.get("news_evidence_present"))
    return bool(news_result_count)
