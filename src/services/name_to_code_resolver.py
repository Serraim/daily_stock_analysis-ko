# -*- coding: utf-8 -*-
"""
===================================
종목명 → 코드 변환 엔진
===================================

종목명을 코드로 변환: 전역 ``stockDB`` 정확 일치 + AkShare 보강 +
혼합 매칭(부분 문자열/병음/유사 매칭).
"""

from __future__ import annotations

import concurrent.futures
import difflib
import json
import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from src.data.stock_mapping import STOCK_NAME_MAP
from src.services.stock_code_utils import is_code_like, normalize_code

logger = logging.getLogger(__name__)

# AkShare 결과 캐시: (타임스탬프, name_to_code 딕셔너리). TTL이 지나도 stale
# 데이터로 계속 제공하고(stale-while-revalidate), 갱신은 백그라운드 스레드가 맡는다.
_akshare_cache: Optional[tuple[float, Dict[str, str]]] = None
_AKSHARE_CACHE_TTL = 1800  # 30 MIN

# 실패 백오프: 마지막으로 가져오기에 실패한 시각. 실패 캐시를 두지 않으면 네트워크
# 장애 중 매번 다시 요청하게 되고, 느린 타임아웃이 모든 메시지의 응답 지연으로 번진다.
# stale 캐시가 있으면 백오프 구간에도 stale을 제공한다(네트워크 장애 중에도 동작 유지).
# 캐시가 전혀 없는 콜드 스타트일 때만 로컬 DB로 대체한다.
_akshare_failure_cache: Optional[float] = None
_AKSHARE_FAILURE_TTL = 300  # 5 MIN

# 가져오기 타임아웃: akshare의 일부 거래소 요청(상해거래소 GET, 북경거래소
# POST 등)은 타임아웃이 없어, 멈추면(실패가 아니라) 가져오기 스레드가 영영 돌아오지 않는다.
# 이때 예외 경로도, 실패 백오프도 동작하지 않는다. 하위 프로세스로 감싸 시간 상한을 두면
# 멈춘 하위 프로세스는 타임아웃 시점에 terminate/kill 되고 TimeoutError로 올라와 일반 실패 경로로 백오프가 기록된다.
_AKSHARE_FETCH_TIMEOUT = 25.0

# 콜드 스타트 대기 상한: 가져오기는 하위 프로세스에서 _AKSHARE_FETCH_TIMEOUT 안에 끝나고, worker는
# 그 뒤 짧은 정리 단계 안에 반드시 Future를 resolve 한다. 대기 상한을 별도 매직 넘버가 아니라
# 같은 상수에서 계산해, 진행 중인 가져오기와 겹친 요청은 구조적으로 그 결과를 받게 한다. 예전에 따로
# 8s 상수를 썼더니 실측 가져오기 시간 6.6~8.2s와 겹쳐 콜드 스타트 요청이 번번이 변환에 실패했다.
# 여유분은 DataFrame 파싱과 정리 단계용이다. 파일 저장/로그는 깨운 뒤에 하므로 포함하지 않는다. TTL 만료 시에는
# stale-while-revalidate로 대기가 없으므로 이 값은 콜드 스타트에만 영향을 준다.
_AKSHARE_WAIT_COLD_START = _AKSHARE_FETCH_TIMEOUT + 5.0

# 상태 락: 캐시/백오프/진행 중 핸들 읽기·쓰기의 원자성만 보장한다. 락 안의 유일한 IO 예외는
# _try_load_disk_cache_locked의 첫 지연 로드다(프로세스당 한 번, 작은 로컬 파일이라 밀리초
# 수준). 네트워크 가져오기와 파일 저장은 모두 락 밖의 백그라운드 갱신 스레드에서 한다. _db_lock과 중첩되지 않아
# 락 순서 순환이 생기지 않는다.
_state_lock = threading.Lock()

# 진행 중 가져오기 핸들: None이 아니면 이미 백그라운드 스레드가 갱신 중이다. 동시 대기자는 Future의
# 완료 신호를 기다린다(성공/실패 모두 정확히 깨움). 줄 서서 락을 잡고 이중 확인하는 방식이 아니어서 대기와
# 가져오기 시간이 분리되고, 25<30 같은 상수 간 암묵적 약속도 없다.
_akshare_inflight: Optional[concurrent.futures.Future] = None

# 디스크 캐시: 가져오기에 성공하면 원자적으로 저장하고, 재시작 시 stale 데이터로 지연 로드한다. 종목명 목록은
# 거의 바뀌지 않으므로 재시작 후에도 재사용해 "콜드 스타트 대기"를 디스크에도 데이터가 없는 경우로만 줄인다.
# 경로는 data/cache 규칙을 따른다(이 디렉터리는 gitignore 되어 있음).
_AKSHARE_DISK_CACHE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "cache" / "akshare_name_map.json"
)
_akshare_disk_checked = False

# stockDB 읽기/쓰기 락: 의도 해석은 asyncio.to_thread 작업 스레드에서 동시에 실행되므로
# extend_AkShare의 제자리 병합과 stockDB를 순회하는 읽기 경로를 락 없이 두면
# "dictionary changed size during iteration" 오류가 난다. RLock이라 중첩 획득이 가능하다.
_db_lock = threading.RLock()


def _contains_cjk(text: str) -> bool:
    """텍스트에 한중일(CJK) 문자가 있으면 True를 반환한다."""
    return any("\u3400" <= ch <= "\u9fff" for ch in text)


def _normalize_stock_name(name: str) -> str:
    """종목명 통합 정규화: NFKC 폭 정규화(전각 영문/숫자 → 반각) + 모든
    공백 제거.

    토큰화 파이프라인은 사용자 입력에 같은 NFKC를 적용한다(web_intent_tokenizer._preprocess_text
    의 작업 사본). DB 안의 이름이 원본 표기를 그대로 두면(AkShare의 "京东方Ａ" 전각 Ａ,
    "五 粮 液" 내부 공백) 창/조각이 정규화된 입력과 영영 같아지지 않는다. 전체 이름
    정확 일치가 실패할 뿐 아니라 더 짧은 DB 이름이 잘못된 종목으로 잘라 낸다("京东方Ａ" 실패 뒤
    2글자 창이 "京东"에 걸림). 입력 쪽과 DB 쪽은 같은 변환을 거쳐야 한다: 로컬 매핑 초기값,
    AkShare 구성·병합, 디스크 캐시 로드라는 세 입구와 모든 조회 경로가 이 함수를 공유한다
    (디스크 캐시 속 예전 미정규화 데이터도 여기서 정규화). 표시 이름도 정규화 표기로 통일된다
    (token 계층의 "단일 코드 정체성" 원칙과 같음).
    """
    return "".join(unicodedata.normalize("NFKC", name).split())


def _is_code_like(s: str) -> bool:
    """공용 "코드처럼 보이는지" 검사의 하위 호환 래퍼."""
    return is_code_like(s)


def _normalize_code(raw: str) -> Optional[str]:
    """공용 코드 정규화의 하위 호환 래퍼."""
    return normalize_code(raw)


def _build_reverse_map_no_duplicates(
    code_to_name: Dict[str, str],
) -> Dict[str, str]:
    """
    name -> code 매핑을 만든다. 한 이름이 여러 코드에 대응하면(모호하면) 제외한다.
    """
    name_to_codes: Dict[str, Set[str]] = {}
    for code, name in code_to_name.items():
        if not name or not code:
            continue
        name = name.strip()
        if name not in name_to_codes:
            name_to_codes[name] = set()
        name_to_codes[name].add(code)
    # Only include names with exactly one code
    return {name: next(iter(codes)) for name, codes in name_to_codes.items() if len(codes) == 1}


def _build_local_name_indexes(code_to_name: Dict[str, str]) -> Tuple[Dict[str, str], Set[str]]:
    """
    Build cached local lookup structures:
    - unique name -> code
    - ambiguous names that should fail fast
    """
    name_to_codes: Dict[str, Set[str]] = {}
    for code, name in code_to_name.items():
        if not name or not code:
            continue
        normalized_name = _normalize_stock_name(name)
        if not normalized_name:
            continue
        name_to_codes.setdefault(normalized_name, set()).add(code)

    unique_names = {
        name: next(iter(codes))
        for name, codes in name_to_codes.items()
        if len(codes) == 1
    }
    ambiguous_names = {
        name
        for name, codes in name_to_codes.items()
        if len(codes) > 1
    }
    return unique_names, ambiguous_names


_LOCAL_REVERSE_MAP, _LOCAL_AMBIGUOUS_NAMES = _build_local_name_indexes(STOCK_NAME_MAP)


def _akshare_stock_info_worker():
    """하위 프로세스에서 실행: akshare를 불러와 A주 전체 코드표를 가져온다.

    반드시 모듈 수준 함수여야 한다(spawn은 pickle로 정규 이름을 넘김). akshare와
    pandas 같은 무거운 의존성은 하위 프로세스에만 올리고 부모 프로세스는 불러오지 않는다.
    """
    import akshare as ak

    return ak.stock_info_a_code_name()


def _fetch_akshare_df():
    """AkShare 전체 가져오기의 유일한 네트워크 출구(테스트용 이음매).

    data_provider의 하위 프로세스 타임아웃 래퍼(spawn)로 실행한다. 멈춘 네트워크 요청은
    _AKSHARE_FETCH_TIMEOUT 안에 종료되고, 부모 프로세스에서는 TimeoutError로 올라온다.
    akshare 내부의 @lru_cache는 하위 프로세스에만 있으므로, 30분 TTL 만료 뒤
    갱신하면 부모 프로세스는 항상 새 데이터를 받는다.
    """
    from data_provider.akshare_fetcher import _akshare_call_with_timeout

    return _akshare_call_with_timeout(
        _akshare_stock_info_worker,
        timeout=_AKSHARE_FETCH_TIMEOUT,
        call_name="stock_info_a_code_name",
    )


def _build_name_map_from_df(df) -> Dict[str, str]:
    """AkShare의 code/name DataFrame을 모호성이 제거된 name->code 매핑으로 바꾼다."""
    code_to_name = {}
    for _, row in df.iterrows():
        code = row.get("code")
        name = row.get("name")
        if code is None or name is None:
            continue
        code_str = str(code).strip()
        # Strip .SH/.SZ suffix
        if "." in code_str:
            base, suffix = code_str.rsplit(".", 1)
            if suffix.upper() in ("SH", "SZ", "SS") and base.isdigit():
                code_str = base
        code_to_name[code_str] = _normalize_stock_name(str(name))
    return _build_reverse_map_no_duplicates(code_to_name)


def _try_load_disk_cache_locked() -> None:
    """디스크 캐시를 메모리로 지연 로드한다(프로세스당 최대 한 번 시도). 호출자는 _state_lock을 잡고 있어야 한다."""
    global _akshare_cache, _akshare_disk_checked
    if _akshare_disk_checked:
        return
    _akshare_disk_checked = True
    try:
        payload = json.loads(_AKSHARE_DISK_CACHE_PATH.read_text(encoding="utf-8"))
        ts = payload.get("ts")
        raw_map = payload.get("map")
        if isinstance(ts, (int, float)) and isinstance(raw_map, dict):
            # 예전에 저장된 데이터에 미정규화 이름(전각 표기/내부 공백)이 있을 수 있어 로드하면서 정규화
            name_map = {
                _normalize_stock_name(str(k)): str(v)
                for k, v in raw_map.items()
                if k and v
            }
            if name_map:
                _akshare_cache = (float(ts), name_map)
                logger.info(
                    "[NameResolver] AkShare 디스크 캐시 로드됨: "
                    f"{len(name_map)}건, age={time.time() - float(ts):.0f}s"
                )
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"[NameResolver] AkShare 디스크 캐시를 쓸 수 없어 무시: {e}")


def _persist_akshare_map(name_map: Dict[str, str]) -> None:
    """원자적 저장(프로세스마다 고유 tmp 이름 + os.replace). 실패해도 치명적이지 않고 로그만 남긴다.

    tmp 이름에 PID를 섞는다: web과 CLI는 서로 다른 프로세스일 수 있어 같은 tmp 이름을 쓰면
    os.replace 전에 상대가 아직 다 쓰지 않은 파일을 서로 덮어쓴다.
    """
    try:
        path = _AKSHARE_DISK_CACHE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps({"ts": time.time(), "map": name_map}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except Exception as e:
        logger.debug(f"[NameResolver] AkShare 디스크 캐시 쓰기 실패(치명적이지 않음): {e}")


def _spawn_refresh_locked() -> concurrent.futures.Future:
    """백그라운드 갱신 스레드를 시작하고 진행 중 핸들을 등록한다. 호출자는 _state_lock을 잡고 있어야 한다.

    네트워크 가져오기, DataFrame 파싱, 파일 저장은 모두 이 daemon 스레드에서 일어난다. 요청
    경로는 상태를 읽거나 Future를 기다릴 뿐 네트워크 IO는 절대 하지 않는다.
    """
    global _akshare_inflight
    fut: concurrent.futures.Future = concurrent.futures.Future()
    # 먼저 등록하고 시작한다: worker가 start() 반환 전에 끝날 수도 있으므로 정리
    # 분기의 `is fut`가 등록된 핸들을 볼 수 있어야 한다
    _akshare_inflight = fut

    def _worker():
        global _akshare_cache, _akshare_failure_cache, _akshare_inflight
        result: Optional[Dict[str, str]] = None
        try:
            try:
                df = _fetch_akshare_df()
                if df is not None and not df.empty:
                    # 빈 데이터도 실패로 보고 백오프: 곧바로 재시도해도 같은 빈 결과만 나온다
                    result = _build_name_map_from_df(df)
            except Exception as e:
                logger.warning(f"[NameResolver] AkShare fallback failed: {e}")
        finally:
            # 먼저 정리하고 모든 대기자를 깨운 뒤, 로그/파일 저장 같은 best-effort 부수 작업을 한다.
            # 느린 로그 handler나 느린 디스크가 대기자의 결과 수신을 붙잡으면 안 된다(예전에 저장을
            # set_result 앞에 두었더니 디스크가 느릴 때 캐시는 준비됐는데 대기자는 타임아웃으로 변환 실패).
            # finally로 마무리: BaseException이 빠져나가도 핸들/백오프/Future는 반드시
            # 정리해 죽은 핸들을 남기지 않는다(남으면 이후 모든 콜드 스타트 요청이 타임아웃까지 헛기다림).
            with _state_lock:
                now = time.time()
                if result:
                    _akshare_cache = (now, result)
                    _akshare_failure_cache = None
                else:
                    _akshare_failure_cache = now
                    result = None
                if _akshare_inflight is fut:
                    _akshare_inflight = None
            # 성공/실패 모두 모든 대기자를 정확히 깨운다. 실패는 result=None으로 표현
            fut.set_result(result)
            if result:
                logger.info(
                    f"[NameResolver] AkShare cache loaded: {len(result)} name->code mappings"
                )
                _persist_akshare_map(result)

    try:
        threading.Thread(
            target=_worker, name="akshare-name-refresh", daemon=True
        ).start()
    except RuntimeError as e:
        # 스레드 시작 실패(프로세스 스레드 수 고갈 등): 핸들을 되돌리고 대기자를 깨운다
        _akshare_inflight = None
        fut.set_result(None)
        logger.warning(f"[NameResolver] AkShare 갱신 스레드 시작 실패: {e}")
    return fut


def _get_akshare_name_to_code() -> Optional[Dict[str, str]]:
    """AkShare name->code 가져오기: 신선한 캐시는 바로 읽고, 만료되면 stale-while-revalidate
    (예전 값을 즉시 반환 + 백그라운드 갱신). 콜드 스타트는 진행 중 Future를 제한 시간 동안 기다리고, 실패 시 백오프.

    요청 경로가 가장 오래 막히는 경우는 콜드 스타트 대기(_AKSHARE_WAIT_COLD_START)뿐이다. TTL 만료
    요청은 대기가 없고, 네트워크 IO는 전부 백그라운드 갱신 스레드에서 한다.
    """
    with _state_lock:
        if _akshare_cache is None:
            _try_load_disk_cache_locked()
        now = time.time()
        if _akshare_cache is not None and (now - _akshare_cache[0]) < _AKSHARE_CACHE_TTL:
            return _akshare_cache[1]
        stale_map = _akshare_cache[1] if _akshare_cache is not None else None
        in_backoff = (
            _akshare_failure_cache is not None
            and (now - _akshare_failure_cache) < _AKSHARE_FAILURE_TTL
        )
        fut = _akshare_inflight
        if fut is None and not in_backoff:
            fut = _spawn_refresh_locked()
    if stale_map is not None:
        # stale-while-revalidate: TTL은 원래 오래된 값을 허용한다는 뜻이라 만료 순간에 기다려도
        # 얻는 게 없다. 예전 값을 돌려주고, 다음 호출이 백그라운드에서 갱신된 새 캐시를 쓴다.
        return stale_map
    if fut is None:
        # 콜드 스타트이면서 실패 백오프 구간: 로컬 DB로 평소처럼 제공
        return None
    try:
        result = fut.result(timeout=_AKSHARE_WAIT_COLD_START)
    except concurrent.futures.TimeoutError:
        # 정상이라면 올 수 없는 곳: 가져오기에는 상한이 있고 worker는 finally에서 반드시
        # resolve 한다. 여기에 왔다면 worker가 약속을 어긴 것이다(하위 프로세스 kill 자체가 멈춘 경우 등).
        logger.warning(
            "[NameResolver] 진행 중인 AkShare 가져오기가 마감 시간이 지나도 resolve 되지 않음"
            f"({_AKSHARE_WAIT_COLD_START:g}s), 이번에는 로컬 DB로 변환"
        )
        return None
    except Exception as e:
        # worker는 실패를 result=None으로 표현하므로 여기는 Future 내부 예외뿐이다
        logger.warning(f"[NameResolver] 진행 중인 AkShare 가져오기 대기 중 예외: {e}")
        return None
    return result


def warmup_akshare_cache() -> None:
    """프로세스 시작 예열: 백그라운드 스레드로 변환 체인을 한 번 채운다(멱등, 비차단).

    디스크 캐시가 있으면 네트워크 없이 로드하고, 없으면 백그라운드에서 한 번만 가져온다. 콜드 스타트 대기는
    이 daemon 스레드 안에서 일어나 호출자를 막지 않는다. 여러 번 호출해도 같은 진행 중 핸들을 공유해
    네트워크 가져오기가 여러 번 일어나지 않는다.
    """

    def _warm():
        try:
            _get_akshare_name_to_code()
        except Exception as e:  # noqa: BLE001 - 예열은 best-effort여야 함
            logger.warning(f"[NameResolver] AkShare 예열 실패: {e}")

    threading.Thread(target=_warm, name="akshare-warmup", daemon=True).start()


# =========================================================================
# Stock — immutable code/name/market value object
# =========================================================================


@dataclass(frozen=True)
class Stock:
    """종목 항목: code / name / market("a" | "hk" | "us")."""

    code: str
    name: str = ""
    market: str = ""


# =========================================================================
# stockDB — 전역 code->name 데이터베이스, AkShare A주 데이터로 보강
# =========================================================================


stockDB: Dict[str, str] = {
    # 초기값부터 정규화(입력 쪽 NFKC와 같은 변환): 원본 데이터의 전각 표기/내부 공백을
    # DB 안으로 가져오지 않는다
    code: _normalize_stock_name(name) for code, name in STOCK_NAME_MAP.items()
}

# 기존 코드의 이름이 AkShare에서 현재 공식 이름으로 바뀌면 예전 이름을 별칭으로 남겨
# 종목 이름 변경 후에도 예전 이름으로 찾을 수 있게 한다.
stockAliases: Dict[str, Set[str]] = {}

_MARKET_ORDER: Dict[str, int] = {"a": 0, "hk": 1, "us": 2}

# 이미 병합한 AkShare 캐시 객체(멱등 단축: 같은 캐시를 두 번 병합하지 않음)
_akshare_merged: Optional[Dict[str, str]] = None


def extend_AkShare() -> bool:
    """AkShare A주 전체 데이터로 stockDB를 보강한다(멱등, 30분 캐시).

    Returns:
        True — stockDB에 새 항목이 실제로 들어갔거나 기존 코드의 이름이 바뀐 경우.
        False — 보강할 필요 없음(같은 캐시를 이미 병합 / 가져오기 실패 / 빈 데이터 /
        변화 없음).
    """
    global _akshare_merged
    akshare_map = _get_akshare_name_to_code()
    if not akshare_map:
        return False
    # 병합 구간 전체를 락으로 감싼다: 읽기 경로의 stockDB 순회와 직렬화되고, "이미 병합한 객체" 판정도 원자적이다.
    # 네트워크 가져오기(위)는 락 밖에 둔다.
    with _db_lock:
        if _akshare_merged is akshare_map:
            return False
        changed = False
        # akshare_map은 name->code 역방향 매핑이고 stockDB는 code->name이다. 이름을
        # 같은 방식으로 정규화(NFKC 폭 + 내부 공백 제거)한 뒤 비교/저장해, 정규화된
        # 입력/로컬 표기와 가짜 이름 변경(쓸데없는 별칭)이 생기지 않게 한다. 디스크 캐시 속 예전
        # 미정규화 데이터도 여기서 정규화
        for name, code in akshare_map.items():
            compact = _normalize_stock_name(name)
            if not compact:
                continue
            if code not in stockDB:
                stockDB[code] = compact
                changed = True
            elif stockDB[code] != compact:
                # 종목 이름 변경: 예전 이름을 별칭으로 남기고 AkShare 현재 공식 이름으로 갱신.
                stockAliases.setdefault(code, set()).add(stockDB[code])
                stockDB[code] = compact
                changed = True
        _akshare_merged = akshare_map
        if changed:
            # stockDB 값이 바뀌거나 별칭이 바뀌어도 len(stockDB)는 그대로일 수 있으므로
            # 이름/병음 캐시를 직접 무효화해야 한다. 안 그러면 이름 변경 후 새 이름이 보이지 않는다.
            _names_cache[:] = [None, None, None]
            _pinyin_cache[:] = [None, None]
        return changed


# =========================================================================
# 이름/병음 캐시 —— (database 객체, len)을 키로 쓴다: DB에 무엇을 넣거나
# 지우면 자동으로 무효화되므로 직접 초기화할 필요가 없다.
# =========================================================================


_names_cache: List = [None, None, None]  # [database, len(database), names]
_pinyin_cache: List = [None, None]  # [names, pinyins]


def _database_names(database: Dict[str, str]) -> List[str]:
    """*database*의 이름 목록(중복 제거, 순서 유지, 캐시 사용).

    canonical(공식) 이름 외에 stockDB의 예전 이름 별칭도 포함한다. 그래서 예전 이름도
    정확·부분 문자열·병음·유사 매칭에 참여할 수 있다.
    """
    with _db_lock:
        if _names_cache[0] is database and _names_cache[1] == len(database):
            return _names_cache[2]
        names = list(dict.fromkeys(database.values()))
        if database is stockDB:
            for aliases in stockAliases.values():
                for alias in aliases:
                    if alias not in names:
                        names.append(alias)
        _names_cache[:] = [database, len(database), names]
        return names


def _database_pinyins(
    database: Dict[str, str], names: Optional[List[str]] = None
) -> List[str]:
    """*names*와 순서를 맞춘 전체 병음 소문자 목록(캐시 사용).

    바깥 스냅샷을 넘기면 그 스냅샷으로 만들어, 호출자의 로컬 names와 출처·순서가 같도록 보장한다.
    동시 병합 중 목록을 두 번 가져와 zip 짝이 어긋나는 일을 막는다.
    """
    if names is None:
        names = _database_names(database)
    with _db_lock:
        if _pinyin_cache[0] is not names:
            try:
                from pypinyin import lazy_pinyin

                pinyins = ["".join(lazy_pinyin(name)).lower() for name in names]
            except Exception:
                pinyins = [""] * len(names)
            _pinyin_cache[:] = [names, pinyins]
        return _pinyin_cache[1]


# =========================================================================
# 이름 매칭 보조 함수
# =========================================================================


def _exact_names(fragment: str, database: Dict[str, str]) -> List[str]:
    """database 이름 중 *fragment*와 대소문자 구분 없이 정확히 일치하는 결과를 반환한다."""
    fragment_lower = fragment.lower()
    return [name for name in _database_names(database) if name.lower() == fragment_lower]


def _is_single_char_typo(input_name: str, candidate_name: str) -> bool:
    """두 이름이 한 글자 위치만 다르면 True를 반환한다."""
    if not input_name or not candidate_name:
        return False
    if len(input_name) != len(candidate_name):
        return False
    # Keep typo fallback conservative: only for names with enough signal.
    if len(input_name) < 3:
        return False
    diff = sum(1 for a, b in zip(input_name, candidate_name) if a != b)
    return diff == 1


# 병음 부분 문자열 매칭 최소 길이: 병음 글자는 음절 단위로 아주 흔해서, 너무 짧은 조각(o/k/ai/ma)은
# 관계없는 이름의 병음에 대량으로 걸려 평범한 영어 입력을 종목으로 잘못 해석한다.
_MIN_PINYIN_FRAGMENT_LEN = 5


def _fix_name(fragment: str, database: Dict[str, str]) -> List[str]:
    """혼합 매칭으로 이름 조각을 전체 종목명으로 변환한다.

    전략 순서:
    1. 정확 일치(대소문자 구분 없음)
    2. 부분 문자열 일치(대소문자 구분 없음, 조각에 CJK 문자가 2개 이상, 예: 茅台 -> 贵州茅台)
    3. 병음 부분 문자열 일치(예: "maotai" ⊂ "guizhoumaotai")
    4. difflib 유사 매칭(cutoff 0.8, 추가로 0.7의 보수적인 한 글자 오타 대체,
       예: 贵州茅苔 -> 贵州茅台)
    """
    if not fragment:
        return []
    fragment_lower = fragment.lower()
    names = _database_names(database)

    # 1. Exact match
    exact = [name for name in names if name.lower() == fragment_lower]
    if exact:
        return exact

    # 2. Substring match
    if sum(1 for ch in fragment if "\u3400" <= ch <= "\u9fff") >= 2:
        matches = [name for name in names if fragment_lower in name.lower()]
        if matches:
            return matches

    # 3. Pinyin substring match — 순수 ASCII 조각에만 적용
    # (영어 병음 입력용: "maotai" ⊂ "guizhoumaotai"). CJK 조각은
    # 병음으로 바꾸면 단위가 엉망이 된다: 실사 + 조사("阿里的" → "alide")가 딱 5글자로
    # 최소 길이 관문을 통과해 엉뚱한 전체 이름("alide" ⊂ "zhongdalide" 中大力德)과
    # 부분 문자열 충돌이 난다. 게다가 CJK의 정상 사례는 나머지 세 단계(정확/부분 문자열/difflib)가 이미 처리한다
    if _contains_cjk(fragment):
        fragment_pinyin = ""
    else:
        try:
            from pypinyin import lazy_pinyin

            fragment_pinyin = "".join(lazy_pinyin(fragment)).lower()
        except Exception:
            fragment_pinyin = ""
    if len(fragment_pinyin) >= _MIN_PINYIN_FRAGMENT_LEN:
        matches = [
            name
            for name, pinyin in zip(names, _database_pinyins(database, names))
            if fragment_pinyin in pinyin
        ]
        if matches:
            return matches

    # 4. Fuzzy match
    if len(fragment) > 2:
        matches = difflib.get_close_matches(fragment, names, n=5, cutoff=0.8)
        if matches:
            return matches
        typo_matches = difflib.get_close_matches(fragment, names, n=5, cutoff=0.7)
        matches = [m for m in typo_matches if _is_single_char_typo(fragment, m)]
        if matches:
            return matches

    return []


def _infer_code_market(code: str) -> Optional[str]:
    """코드 형식으로 시장을 추정: 숫자 6자리→"a", 숫자 5자리→"hk", 영문자→"us"."""
    c = code.strip()
    if c.isdigit():
        return {5: "hk", 6: "a"}.get(len(c))
    return "us" if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", c) else None


def _find_codes_for_name(name: str, database: Dict[str, str]) -> List[Tuple[str, str]]:
    """*database*에서 *name*에 대응하는 모든 (code, market) 조합을 찾는다."""
    results: List[Tuple[str, str]] = []
    # 락을 잡고 순회: extend_AkShare의 동시 쓰기와 직렬화
    with _db_lock:
        for code, mapped_name in database.items():
            if mapped_name == name or (
                database is stockDB and name in stockAliases.get(code, set())
            ):
                market = _infer_code_market(code)
                if market:
                    results.append((code, market))
    return results


# =========================================================================
# 공개 API
# =========================================================================


def resolver_name_to_code_list(name: str) -> List[Stock]:
    """종목명을 일치하는 ``Stock`` 항목(최대 5개)으로 변환한다. 종목 코드는 아직 변환하지 않는다.

    1. CJK 입력이면 AkShare A주 데이터로 ``stockDB``를 보강한다(멱등, 실패 백오프 포함).
       CJK가 아닌 입력은 네트워크 가져오기를 완전히 건너뛴다.
    2. ``stockDB``에서 정확 일치를 찾는다.
    3. 보강된 데이터베이스에서 혼합 매칭(정확/부분 문자열/병음/유사)을 한다.

    결과는 A주 → 홍콩 → 미국 순으로 정렬한다.

    예시:
        "阿里巴巴" → [Stock("09988", "阿里巴巴", "hk"), Stock("BABA", "阿里巴巴", "us")]
        "茅台"     → [Stock("600519", "贵州茅台", "a")]
        "你好世界"  → []
    """
    if not name or not isinstance(name, str):
        return []
    # 조회 입력도 DB와 같은 방식으로 정규화: 원본 형태(전각 표기/내부 공백, 예: AkShare 데이터에서
    # 복사한 "京东方Ａ"/"五 粮 液")도 일반 표기처럼 변환된다
    s = _normalize_stock_name(name)
    # 한 글자는 종목명일 수 없으므로(최소 2글자) 전체 이름표 검색을 건너뛴다
    if len(s) < 2:
        return []

    # A주 이름은 전부 CJK다 —— CJK가 아닌 입력은 네트워크 보강의 이득이 없지만, 로컬
    # 혼합(병음) 매칭에는 참여할 수 있다.
    # 로컬에서 정확히 일치해도 AkShare 보강을 먼저 한다: 로컬에 있는 같은 이름의 홍콩/미국 종목이
    # AkShare의 같은 이름 A주 병합을 막으면 시장 간 후보가 불완전해진다.
    if _contains_cjk(s):
        extend_AkShare()

    full_names = _exact_names(s, stockDB)
    if not full_names:
        full_names = _fix_name(s, stockDB)
    if not full_names:
        return []

    stocks: List[Stock] = []
    seen: Set[str] = set()
    for full_name in full_names:
        for code, market in _find_codes_for_name(full_name, stockDB):
            if code not in seen:
                seen.add(code)
                stocks.append(Stock(code=code, name=stockDB.get(code, full_name), market=market))

    stocks.sort(key=lambda r: _MARKET_ORDER.get(r.market, 99))
    return stocks[:5]


def US_stock_code_match(segment: str) -> List[Stock]:
    """미국 종목 코드 매칭: 영문자 1~5개 ticker이고 로컬 DB에 그 코드가 있을 때만 반환한다.

    평범한 영어 단어(hello/open/...)를 종목 코드로 오인하지 않게 한다.
    """
    if not isinstance(segment, str) or not segment.isascii() or not segment.isalpha():
        return []
    if not 1 <= len(segment) <= 5:
        return []
    upper = segment.upper()
    name = stockDB.get(upper, "")
    return [Stock(code=upper, name=name, market="us")] if name else []


def lookup_stock_by_code(code: str) -> Optional[Stock]:
    """정규화한 코드로 DB를 조회해 (code/name/market) 세 값을 반환한다. 없으면 None.

    형식이 맞다고 존재하는 건 아니다: stockDB에 없으면 None이며 절대 지어내지 않는다(LLM 환각/오래된
    코드를 stocks에 바로 넣으면 안 됨). 로컬 DB의 홍콩 종목 키는 5자리 숫자만("00700")이며, HK 접두
    형태("HK00700")는 접두어를 뗀 키로 자동 재조회한다.
    """
    c = (code or "").strip().upper()
    if not c:
        return None
    with _db_lock:
        name = stockDB.get(c)
        if not name and c.startswith("HK"):
            name = stockDB.get(c[2:])
        if not name:
            return None
    if c.startswith("HK"):
        market = "hk"
    else:
        market = _infer_code_market(c) or ""
    return Stock(code=c, name=name, market=market)


def is_market_db_complete(market: str) -> bool:
    """해당 시장의 이름 DB가 전체 목록으로 확장됐는지(그렇다면 DB에 없으면 코드가 없다고 단정 가능).

    A주: AkShare 전체 목록이 stockDB에 병합됨(extend_AkShare가 성공한 적 있고
    ``_akshare_merged``가 비어 있지 않음). 홍콩/미국: 엄선한 로컬 DB라 전체로 보지 않으며,
    없을 때는 판단을 보류하고 하위 단계에 맡긴다.
    """
    return market == "a" and _akshare_merged is not None


def is_known_stock_name(name: str) -> bool:
    """*name*이 stockDB에 있는 종목 전체 이름(이름 변경 별칭 포함)인지 판단한다.

    로컬 이름표 포함 여부만 보고 AkShare 네트워크 확장은 절대 하지 않는다. 코드 키
    (예: "600519")는 이름 일치로 치지 않는다: 토큰화 파이프라인(web_intent_tokenizer)이 이
    함수로 "인식된 이름 token"을 보호하므로, 코드 형태 텍스트는 코드 추출 단계로 넘어가
    다시 표시돼야 하며 이름으로 취급돼 건너뛰면 안 된다.
    """
    if not isinstance(name, str):
        return False
    s = _normalize_stock_name(name)
    if not s:
        return False
    return s in _database_names(stockDB)


def resolve_name_to_code(name: str) -> Optional[str]:
    """
    Resolve stock name to code.

    Strategy (in order):
    1. If input looks like a code (5-6 digits or 1-5 letters), return it normalized.
    2. Local STOCK_NAME_MAP reverse (exclude ambiguous names).
    3. Pinyin match against local names.
    4. AkShare online fallback (A-shares).
    5. Fuzzy match (difflib).
    6. Return None.

    Args:
        name: Stock name or code string.

    Returns:
        Resolved stock code, or None if ambiguous/failed.
    """
    if not name or not isinstance(name, str):
        return None
    s = _normalize_stock_name(name)
    if not s:
        return None

    # 1. Input looks like code
    if _is_code_like(s):
        return _normalize_code(s)

    # 2. Local reverse map (no duplicates)
    local_reverse = _LOCAL_REVERSE_MAP
    if s in local_reverse:
        return local_reverse[s]
    if s in _LOCAL_AMBIGUOUS_NAMES:
        logger.debug(f"[NameResolver] 로컬 모호 이름에 걸려 None을 바로 반환: {s}")
        return None

    # 3. Pinyin match (exact)
    try:
        from pypinyin import lazy_pinyin

        input_pinyin = "".join(lazy_pinyin(s)).lower()
        for local_name, code in local_reverse.items():
            local_pinyin = "".join(lazy_pinyin(local_name)).lower()
            if input_pinyin == local_pinyin:
                return code
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[NameResolver] Pinyin match failed: {e}")

    # Skip AkShare/fuzzy fallback for non-CJK free text such as random Latin noise.
    # These paths are expensive and only meaningfully help Chinese stock names.
    if not _contains_cjk(s):
        logger.debug(f"[NameResolver] Skip CJK-only fallbacks for non-CJK input: {s}")
        return None

    # 4. AkShare fallback
    akshare_map = _get_akshare_name_to_code()
    if akshare_map and s in akshare_map:
        logger.debug(f"[NameResolver] AkShare 매핑 일치: {s} -> {akshare_map[s]}")
        return akshare_map[s]

    # 5. Fuzzy match (local + akshare, local takes precedence)
    all_name_to_code = dict(local_reverse)
    if akshare_map:
        all_name_to_code.update(akshare_map)
    # Skip fuzzy matching for very short inputs (<=2 chars) to avoid false positives,
    # e.g. '中国' matching arbitrary company names in a pool of 5000+ stocks.
    # Use a higher cutoff (0.8) to reduce mis-hits on longer inputs as well.
    if len(s) > 2:
        names = list(all_name_to_code.keys())
        matches = difflib.get_close_matches(s, names, n=1, cutoff=0.8)
        if matches:
            logger.debug(f"[NameResolver] 유사 매칭 일치: input={s}, matched={matches[0]}")
            return all_name_to_code[matches[0]]

        # Conservative fallback for one-character typo in medium/long names.
        # This keeps the strict default threshold while fixing obvious misspellings
        # such as "贵州茅苔" -> "贵州茅台".
        typo_matches = difflib.get_close_matches(s, names, n=1, cutoff=0.7)
        if typo_matches and _is_single_char_typo(s, typo_matches[0]):
            logger.debug(f"[NameResolver] 한 글자 오타 대체 일치: input={s}, matched={typo_matches[0]}")
            return all_name_to_code[typo_matches[0]]

    logger.debug(f"[NameResolver] 변환 실패: {s}")
    return None
