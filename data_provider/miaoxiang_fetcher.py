"""
묘상(MiaoXiang) 금융 데이터 소스 — 동방재부(Eastmoney) 묘상 Skills MX_API 래퍼

역할:
    공개 시세 API가 불안정할 때 빠진 세부 데이터(종목 자금 흐름 / 매물대 분포)를 채움,
    일봉 K선 주 경로에는 참여하지 않음(`_DAILY_MARKET_FETCHER_SUPPORT`의 지원 시장이 빈 집합).

데이터 출처:
    묘상 퀀트 API(MX_API), 자연어 질의로 구조화된 표를 돌려받음:
    POST https://mkapi2.dfcfs.com/finskillshub/api/claw/query
    Header: apikey: <MX_APIKEY>
    Body:   {"toolQuery": "<자연어 질의>"}

사용 조건:
    MX_APIKEY를 설정하면 DataFetcherManager가 자동으로 생성함.
"""

import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from .base import (
    BaseFetcher,
    DataFetchError,
    _is_etf_code,
    _is_non_cn_request,
    normalize_stock_code,
)
from .realtime_types import ChipDistribution

logger = logging.getLogger(__name__)

# 묘상 API 기본 주소(중국 내 직접 연결)
MX_API_BASE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"

# 조회 결과 캐시 TTL(초): 같은 종목의 자금 흐름/매물대는 잠시 재사용해 사용량을 줄임
MX_CACHE_TTL_SECONDS = 300.0
# 연속 요청 사이 최소 간격(초): 자연어 API에 과부하를 주지 않기 위함
MX_MIN_REQUEST_INTERVAL_SECONDS = 0.3





def _parse_number(text: Any) -> Optional[float]:
    """'13.91' / '13.91元' / '-1.5' 같은 텍스트에서 숫자를 뽑아냄."""
    if text is None:
        return None
    s = str(text).strip().replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def _parse_money_yuan(text: Any) -> Optional[float]:
    """'-93.64万元' / '1.2亿' / '-493.5万'을 위안 단위 실수로 변환."""
    if text is None:
        return None
    s = str(text).strip().replace(",", "")
    if "%" in s or "％" in s:
        return None
    val = _parse_number(s)
    if val is None:
        return None
    if "亿" in s:
        val *= 1e8
    elif "万" in s:
        val *= 1e4
    return val


def _parse_ratio(text: Any) -> Optional[float]:
    """'83.24%'를 0.8324로 변환. '0.83'은 이미 소수로 봄."""
    val = _parse_number(text)
    if val is None:
        return None
    if "%" in str(text or ""):
        val = val / 100.0
    if val > 1.0:
        # 예비 처리: 일부 질의는 % 없이 83.24로 돌려줄 수 있음
        val = val / 100.0
    return val


class MiaoxiangFetcher(BaseFetcher):
    """묘상 금융 데이터 소스(자금 흐름 / 매물대 분포 보조 소스)"""

    name = "MiaoxiangFetcher"
    # 이 보조 소스가 자금 흐름을 제공할 수 있는 시장을 선언. 탐지와 예산 배분은 이 값을 기준으로 판단,
    # 다른 시장만 지원하는 같은 이름의 메서드(예: 홍콩 주식 전용 FutuFetcher)를 이 시장의 보조 소스로 잘못 보지 않게 함
    capital_flow_markets = {"cn"}
    # Admission is shared by chip/flow queries and by fresh manager instances.
    # Never queue another quota-consuming request behind an abandoned worker.
    _request_lock = threading.Lock()

    def __init__(
        self,
        api_key: str = "",
        priority: int = 6,
        timeout: int = 10,
        base_url: str = MX_API_BASE_URL,
        cache_ttl: float = MX_CACHE_TTL_SECONDS,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.priority = int(priority)
        self.timeout = int(timeout)
        self.base_url = base_url.rstrip("/")
        self._cache_ttl = float(cache_ttl)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()
        self._last_request_ts = 0.0

    def is_available_for_request(self, capability: str = "") -> bool:
        """Keep this supplement-only provider out of every daily-data route."""
        return capability != "daily_data"

    # ------------------------------------------------------------------
    # MX_API 클라이언트
    # ------------------------------------------------------------------

    def _query_tables(self, cache_key: str, tool_query: str) -> List[Dict[str, Any]]:
        """자연어 질의를 한 번 실행해 dataTableDTOList를 돌려줌(TTL 캐시 적용)."""
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and (time.time() - cached[0]) < self._cache_ttl:
                return cached[1]

        if not self._request_lock.acquire(blocking=False):
            raise DataFetchError("妙想 API 请求仍在执行，跳过本次补充查询")
        try:
            wait = MX_MIN_REQUEST_INTERVAL_SECONDS - (time.time() - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            try:
                response = requests.post(
                    self.base_url,
                    headers={"apikey": self.api_key, "Content-Type": "application/json"},
                    json={"toolQuery": tool_query},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise DataFetchError(f"묘상 API 요청 실패: {exc}") from exc
            finally:
                self._last_request_ts = time.time()
        finally:
            self._request_lock.release()

        if payload.get("status") != 0:
            message = str(payload.get("message", ""))[:120]
            raise DataFetchError(f"묘상 API 오류 응답: status={payload.get('status')} {message}")

        # 공식 응답 형태 두 가지를 모두 지원(정해진 후보 경로만 보고, 재귀 탐색은 하지 않음):
        #   A. 실측 형태:  data.data.searchDataResultDTO.dataTableDTOList
        #   B. 공개 문서:  data.dataTableDTOList
        tables: list = []
        data_node = payload.get("data")
        if isinstance(data_node, dict):
            candidate_a = (
                data_node.get("data", {})
                if isinstance(data_node.get("data"), dict) else {}
            ).get("searchDataResultDTO", {})
            candidate_a = candidate_a.get("dataTableDTOList") if isinstance(candidate_a, dict) else None
            candidate_b = data_node.get("dataTableDTOList")
            for candidate in (candidate_a, candidate_b):
                if isinstance(candidate, list) and candidate:
                    tables = [t for t in candidate if isinstance(t, dict)]
                    break
        if not tables:
            raise DataFetchError("묘상 API가 데이터 표를 돌려주지 않음")

        with self._cache_lock:
            self._cache[cache_key] = (time.time(), tables)
        return tables

    @staticmethod
    def _table_name_map(table_dto: Dict[str, Any]) -> Dict[str, Any]:
        """Use the same numeric-key/list mapping for selection and row parsing."""
        name_map = table_dto.get("nameMap") or {}
        if isinstance(name_map, list):
            name_map = {str(i): v for i, v in enumerate(name_map)}
        return name_map

    @staticmethod
    def _table_rows(table_dto: Dict[str, Any]) -> List[Dict[str, str]]:
        """MX 표(headName이 행 축 + 지표 열 배열)를 [{label: value}] 행 목록으로 바꿈."""
        table = table_dto.get("table") or {}
        name_map = MiaoxiangFetcher._table_name_map(table_dto)
        heads = table.get("headName") or []
        rows: List[Dict[str, str]] = []
        for key, values in table.items():
            if key == "headName" or not isinstance(values, list):
                continue
            label = str(name_map.get(key, name_map.get(str(key), key)))
            for idx, value in enumerate(values):
                while len(rows) <= idx:
                    rows.append({})
                rows[idx][label] = "" if value is None else str(value)
        # 행마다 날짜(headName)를 남겨 자금 흐름을 날짜별로 합산하기 쉽게 함
        for idx, head in enumerate(heads):
            while len(rows) <= idx:
                rows.append({})
            rows[idx]["_date"] = str(head)
        return rows

    def _table_labels(self, table_dto: Dict[str, Any]) -> List[str]:
        """표에 들어 있는 모든 지표 이름을 돌려줌(nameMap으로 매핑)."""
        table = table_dto.get("table") or {}
        name_map = self._table_name_map(table_dto)
        labels: List[str] = []
        for key in table:
            if key == "headName":
                continue
            labels.append(str(name_map.get(key, name_map.get(str(key), key))))
        return labels

    def _find_table_by_label(self, tables: List[Dict[str, Any]], keyword: str) -> Optional[Dict[str, Any]]:
        """지정한 지표 이름이 있는 표를 돌려줌. 여러 개면 행이 가장 많은 표 우선(현재 스냅숏보다 시계열 우선)."""
        best: Optional[Dict[str, Any]] = None
        best_rows = -1
        for table_dto in tables:
            if not any(keyword in label for label in self._table_labels(table_dto)):
                continue
            rows = len((table_dto.get("table") or {}).get("headName") or [])
            if rows > best_rows:
                best = table_dto
                best_rows = rows
        return best

    def _find_table_by_label_score(
        self,
        tables: List[Dict[str, Any]],
        required_keyword: str,
        wanted_keywords: List[str],
    ) -> Optional[Dict[str, Any]]:
        """자연어 응답의 표 구성은 들쭉날쭉함: '목표 필드 일치 개수'로 점수를 매겨 표를 고르고, 행이 적은 표 우선(시계열보다 스냅숏 우선)."""
        best: Optional[Dict[str, Any]] = None
        best_key = (-1, 10**9)
        for table_dto in tables:
            labels = self._table_labels(table_dto)
            if not any(required_keyword in label for label in labels):
                continue
            score = sum(1 for kw in wanted_keywords if any(kw in label for label in labels))
            rows = len((table_dto.get("table") or {}).get("headName") or [])
            if (score, -rows) > best_key:
                best = table_dto
                best_key = (score, -rows)
        return best

    # ------------------------------------------------------------------
    # 매물대 분포
    # ------------------------------------------------------------------

    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        묘상 API로 매물대 분포 핵심 지표를 받아옴:
        수익 비율 / 평균 단가 / 90% 집중도 / 70% 집중도.

        Returns:
            ChipDistribution(source=miaoxiang). 실패하면 DataFetchError 발생.
        """
        stock_code = normalize_stock_code(stock_code)
        if _is_non_cn_request(stock_code) or _is_etf_code(stock_code):
            logger.debug(f"[API 건너뜀] {stock_code} A주 개별 종목이 아니라 매물대 분포 데이터 없음")
            return None

        tables = self._query_tables(
            f"chip:{stock_code}",
            f"{stock_code} 获利比例 平均成本 90%筹码集中度 70%筹码集中度",
        )
        target = self._find_table_by_label_score(
            tables,
            required_keyword="平均成本",
            wanted_keywords=["获利比例", "90%筹码集中度", "70%筹码集中度"],
        )
        if target is None:
            target = self._find_table_by_label(tables, "筹码")
        if target is None:
            raise DataFetchError("묘상 API 매물대 분포 응답에 쓸 수 있는 표가 없음")

        rows = self._table_rows(target)
        if not rows:
            raise DataFetchError("묘상 API 매물대 분포 표가 비어 있음")
        row = rows[0]

        avg_cost = _parse_number(row.get("平均成本"))
        profit_ratio = _parse_ratio(row.get("获利比例"))
        concentration_90 = _parse_ratio(row.get("90%筹码集中度"))
        concentration_70 = _parse_ratio(row.get("70%筹码集中度"))

        if avg_cost is None or avg_cost <= 0:
            raise DataFetchError(f"묘상 API 매물대 분포 평균 단가가 잘못됨: {row}")

        chip = ChipDistribution(
            code=stock_code,
            date=str(row.get("_date", "")).split(" ")[0],
            source="miaoxiang",
        )
        chip.avg_cost = float(avg_cost)
        if profit_ratio is not None:
            chip.profit_ratio = float(profit_ratio)
        if concentration_90 is not None:
            chip.concentration_90 = float(concentration_90)
        if concentration_70 is not None:
            chip.concentration_70 = float(concentration_70)
        return chip

    # ------------------------------------------------------------------
    # 종목 자금 흐름
    # ------------------------------------------------------------------

    def get_capital_flow(self, stock_code: str, top_n: int = 5) -> Dict[str, Any]:
        """
        묘상 API로 종목의 주력 자금 흐름을 받아옴:
        오늘 주력 순유입 + 최근 5일/10일 주력 순유입 합계.

        Returns:
            AkshareFundamentalAdapter.get_capital_flow와 같은 구조의 payload.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "stock_flow": {},
            "sector_rankings": {"top": [], "bottom": []},
            "source_chain": [],
            "errors": [],
        }
        stock_code = normalize_stock_code(stock_code)
        if _is_non_cn_request(stock_code) or _is_etf_code(stock_code):
            return result

        try:
            tables = self._query_tables(
                f"flow:{stock_code}",
                f"{stock_code} 近10日每日主力净流入资金",
            )
        except DataFetchError as exc:
            result["errors"].append(f"miaoxiang: {exc}")
            return result
        # Natural-language responses may include prices or ratios before the amount.
        # Only explicit monetary metrics may feed currency-valued stock_flow fields.
        amount_labels = {"主力净流入", "主力净流入资金", "主力净流入金额"}
        amount_tables = [
            table for table in tables
            if any(label in amount_labels for label in self._table_labels(table))
        ]
        target = self._find_table_by_label(amount_tables, "主力净流入")
        if target is None:
            result["errors"].append("miaoxiang: no capital flow table")
            return result

        rows = self._table_rows(target)
        series: List[Tuple[str, Optional[float]]] = []
        for row in rows:
            label = next((k for k in row if k in amount_labels), None)
            value = _parse_money_yuan(row.get(label)) if label is not None else None
            # Keep missing observations in their original trading window; dropping
            # them would backfill today's value or compress a 5/10-day aggregate.
            series.append((str(row.get("_date", "")), value))

        if not series or all(value is None for _, value in series):
            result["errors"].append("miaoxiang: empty capital flow series")
            return result

        # headName은 보통 날짜 역순(최신이 먼저)이라, 합산이 맞도록 여기서 날짜순으로 직접 정렬
        series.sort(key=lambda item: item[0], reverse=True)
        latest = series[0][1]
        # 기간 필드는 거래일 데이터가 다 있을 때만 출력함. 일부 기간 합계를
        # 5일/10일 순유입으로 잘못 표시하지 않기 위함(이력이 짧은 신규 상장주는 잘못된 중기 신호를 줄 수 있음)
        def window_sum(size: int) -> Optional[float]:
            values = [value for _, value in series[:size]]
            if len(values) < size or any(value is None for value in values):
                return None
            return sum(values)

        inflow_5d = window_sum(5)
        inflow_10d = window_sum(10)

        result["stock_flow"] = {
            "main_net_inflow": latest,
            "inflow_5d": inflow_5d,
            "inflow_10d": inflow_10d,
        }
        result["status"] = "partial"
        result["source_chain"].append("miaoxiang:capital_flow")
        return result

    # ------------------------------------------------------------------
    # 일봉 주 경로: 명시적으로 지원 안 함(빨리 실패해서 대체 경로 시간을 잡아먹지 않게 함)
    # ------------------------------------------------------------------

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError("MiaoxiangFetcher는 일봉 시세 데이터를 제공하지 않음(보조 전용 데이터 소스)")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise DataFetchError("MiaoxiangFetcher는 일봉 시세 데이터를 제공하지 않음(보조 전용 데이터 소스)")
