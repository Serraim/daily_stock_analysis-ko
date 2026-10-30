# -*- coding: utf-8 -*-
"""
===================================
종목 데이터 API
===================================

역할:
1. POST /api/v1/stocks/extract-from-image 이미지에서 종목 코드 추출
2. POST /api/v1/stocks/parse-import CSV/Excel/클립보드 해석
3. GET /api/v1/stocks/{code}/quote 실시간 시세 API
4. GET /api/v1/stocks/{code}/history 과거 시세 API
"""

import logging
from typing import Optional
import re

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, Depends

from api.deps import get_system_config_service

from api.v1.schemas.stocks import (
    ExtractFromImageResponse,
    ExtractItem,
    KLineData,
    StockHistoryResponse,
    StockProfileResponse,
    StockQuote,
)
from api.v1.schemas.history import WatchlistRequest, WatchlistResponse
from api.v1.schemas.common import ErrorResponse
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    extract_stock_codes_from_image,
)
from src.services.import_parser import (
    MAX_FILE_BYTES,
    parse_import_from_bytes,
    parse_import_from_text,
)
from src.services.stock_service import StockService
from src.services.stock_profile_service import InvalidStockProfileCode, StockProfileService
from src.services.run_diagnostics import sanitize_diagnostic_text
from src.services.stock_list_parser import split_stock_list
from src.services.system_config_service import SystemConfigService
from data_provider.base import normalize_stock_code

logger = logging.getLogger(__name__)

router = APIRouter()

# 반드시 /{stock_code} 라우트보다 먼저 정의해야 함
ALLOWED_MIME_STR = ", ".join(ALLOWED_MIME)


def _read_watchlist_codes(service: SystemConfigService) -> list:
    """Read STOCK_LIST codes as-is (no normalization)."""
    config_data = service.get_config(include_schema=False)
    stock_list_str = ""
    for item in config_data.get("items", []):
        if item.get("key") == "STOCK_LIST":
            stock_list_str = str(item.get("value", ""))
            break
    return split_stock_list(stock_list_str)


def _write_watchlist_codes(service: SystemConfigService, codes: list) -> None:
    """Persist stock codes to STOCK_LIST as-is (no normalization)."""
    config_data = service.get_config(include_schema=False)
    config_version = config_data.get("config_version", "")
    service.update(
        config_version=config_version,
        items=[{"key": "STOCK_LIST", "value": ",".join(codes)}],
        mask_token="******",
        reload_now=True,
    )


# Stock code validation patterns (aligned with frontend validateStockCode)
_STOCK_CODE_RE = re.compile(
    r"^(?:\d{6}"                              # A-share 6-digit
    r"|(?:SH|SZ|BJ)\d{6}"                     # exchange-prefixed A-share
    r"|\d{6}\.(?:SH|SZ|SS|BJ)"                # exchange-suffixed A-share
    r"|\d{1,5}\.HK"                           # HK suffix format
    r"|HK\d{1,5}"                             # HK prefix format
    r"|\d{5}"                                 # bare 5-digit HK code
    r"|\d{4,5}\.T"                            # Japan Yahoo suffix format
    r"|\d{6}\.(?:KS|KQ)"                     # Korea Yahoo suffix format
    r"|\d{4,6}\.(?:TW|TWO)"                  # Taiwan Yahoo suffix format
    r"|[A-Z]{1,5}(?:\.(?:US|[A-Z]))?"         # US ticker
    r")$",
    re.IGNORECASE,
)


def _validate_and_normalize_stock_code(code: str) -> str:
    """Validate stock code format and return canonical form.

    Raises HTTPException(400) if the code does not match supported formats.
    """
    stripped = code.strip()
    if not stripped:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_stock_code", "message": "종목 코드가 비어 있어요"},
        )
    if not _STOCK_CODE_RE.match(stripped):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_stock_code",
                "message": f"'{stripped}' 은(는) 올바른 종목 코드 형식이 아니에요",
            },
        )
    return normalize_stock_code(stripped)


def _watchlist_match_key(code: str) -> str:
    """Return the equivalence key used for watchlist add/remove matching."""
    normalized = normalize_stock_code(code.strip())
    if re.fullmatch(r"\d{5}", normalized):
        return f"HK{normalized}"
    return normalized.upper()


@router.post(
    "/extract-from-image",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "추출한 종목 코드"},
        400: {"description": "잘못된 이미지", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="이미지에서 종목 코드 추출",
    description="스크린샷/이미지를 올리면 Vision LLM 으로 종목 코드를 뽑아냅니다. JPEG, PNG, WebP, GIF 지원, 최대 5MB.",
)
def extract_from_image(
    file: Optional[UploadFile] = File(None, description="이미지 파일 (폼 필드 이름 file)"),
    include_raw: bool = Query(False, description="결과에 LLM 원본 응답을 넣을지 여부"),
) -> ExtractFromImageResponse:
    """
    올린 이미지에서 종목 코드 추출 (Vision LLM 사용).

    이미지는 폼 필드 file 로 올리세요. 우선순위: Gemini / Anthropic / OpenAI (먼저 쓸 수 있는 것).
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "파일이 없어요. 폼 필드 file 로 이미지를 올려 주세요"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"지원하지 않는 형식: {content_type}. 허용: {ALLOWED_MIME_STR}",
            },
        )

    try:
        # 먼저 제한 크기만큼 읽고, 남은 게 있는지 확인 (넘치면 거부)
        data = file.file.read(MAX_SIZE_BYTES)
        if file.file.read(1):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"이미지가 {MAX_SIZE_BYTES // (1024 * 1024)}MB 제한을 넘었어요",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"업로드 파일 읽기 실패: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": "read_failed", "message": "업로드 파일 읽기 실패"},
        )

    try:
        items, raw_text = extract_stock_codes_from_image(data, content_type)
        extract_items = [
            ExtractItem(code=code, name=name, confidence=conf) for code, name, conf in items
        ]
        codes = [i.code for i in extract_items]
        return ExtractFromImageResponse(
            codes=codes,
            items=extract_items,
            raw_text=raw_text if include_raw else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "extract_failed", "message": str(e)})
    except Exception as e:
        logger.error(f"이미지 추출 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "이미지 추출 실패"},
        )


@router.post(
    "/parse-import",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "해석 결과"},
        400: {"description": "데이터가 없거나 해석 실패", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="CSV/Excel/클립보드 해석",
    description="CSV/Excel 파일을 올리거나 텍스트를 붙여 넣으면 종목 코드를 자동으로 뽑아냅니다. 파일 최대 2MB, 텍스트 최대 100KB.",
)
async def parse_import(request: Request) -> ExtractFromImageResponse:
    """
    CSV/Excel 파일이나 클립보드 텍스트 해석.

    - multipart/form-data + file: 파일 업로드
    - application/json + {"text": "..."}: 붙여 넣은 텍스트
    - file 을 먼저 사용. 둘 다 오면 text 는 무시
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            logger.warning("[parse_import] JSON parse failed: %s", e)
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_json", "message": f"JSON 해석 실패: {e}"},
            )
        text = body.get("text") if isinstance(body, dict) else None
        if not text or not isinstance(text, str):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "text 가 없어요. 이렇게 보내 주세요: {\"text\": \"...\"}"},
            )
        try:
            items = parse_import_from_text(text)
        except ValueError as e:
            text_bytes = len(text.encode("utf-8"))
            logger.warning(
                "[parse_import] parse_import_from_text failed: text_bytes=%d, error=%s",
                text_bytes,
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    elif "multipart" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not hasattr(file, "read"):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "파일이 없어요. 폼 필드 file 을 사용하세요"},
            )
        file_size = getattr(file, "size", None)
        if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"파일이 {MAX_FILE_BYTES // (1024 * 1024)}MB 제한을 넘었어요",
                },
            )
        try:
            data = file.file.read(MAX_FILE_BYTES)
            if file.file.read(1):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "file_too_large",
                        "message": f"파일이 {MAX_FILE_BYTES // (1024 * 1024)}MB 제한을 넘었어요",
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            filename = getattr(file, "filename", None) or ""
            size = getattr(file, "size", None)
            logger.warning(
                "[parse_import] file read failed: filename=%r, size=%s, error=%s",
                filename,
                size,
                e,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "read_failed", "message": "파일 읽기 실패"},
            )
        filename = getattr(file, "filename", None) or ""
        try:
            items = parse_import_from_bytes(data, filename=filename)
        except ValueError as e:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            logger.warning(
                "[parse_import] parse_import_from_bytes failed: filename=%r, ext=%r, bytes=%d, error=%s",
                filename,
                ext,
                len(data),
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "multipart/form-data 로 파일을 올리거나, application/json 으로 다음을 보내 주세요: {\"text\": \"...\"}",
            },
        )

    extract_items = [
        ExtractItem(code=code, name=name, confidence=conf)
        for code, name, conf in items
    ]
    codes = list(dict.fromkeys(i.code for i in extract_items if i.code))
    return ExtractFromImageResponse(codes=codes, items=extract_items, raw_text=None)


@router.get(
    "/watchlist",
    response_model=WatchlistResponse,
    responses={
        200: {"description": "현재 관심종목 목록"},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="관심종목 목록 조회",
    description="현재 STOCK_LIST 설정에 있는 종목 코드를 모두 반환.",
)
def get_watchlist(
    service: SystemConfigService = Depends(get_system_config_service),
) -> WatchlistResponse:
    try:
        codes = _read_watchlist_codes(service)
        return WatchlistResponse(stock_codes=codes, message=f"현재 관심종목 {len(codes)}개")
    except Exception as e:
        logger.error(f"관심종목 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"관심종목 목록 조회 실패: {str(e)}"},
        )


@router.post(
    "/watchlist/add",
    response_model=WatchlistResponse,
    responses={
        200: {"description": "관심종목에 추가됨"},
        400: {"description": "파라미터 오류", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="관심종목에 추가",
    description="지정한 종목 코드를 STOCK_LIST 에 추가.",
)
def add_to_watchlist(
    request: WatchlistRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> WatchlistResponse:
    try:
        validated = _validate_and_normalize_stock_code(request.stock_code)
        codes = _read_watchlist_codes(service)
        existing_keys = [_watchlist_match_key(c) for c in codes]
        if _watchlist_match_key(validated) not in existing_keys:
            codes.append(request.stock_code.strip())
            _write_watchlist_codes(service, codes)
        return WatchlistResponse(stock_codes=codes, message=f"{request.stock_code.strip()} 추가했어요")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"관심종목 추가 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"관심종목 추가 실패: {str(e)}"},
        )


@router.post(
    "/watchlist/remove",
    response_model=WatchlistResponse,
    responses={
        200: {"description": "관심종목에서 삭제됨"},
        400: {"description": "파라미터 오류", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="관심종목에서 삭제",
    description="STOCK_LIST 에서 지정한 종목 코드를 뺌.",
)
def remove_from_watchlist(
    request: WatchlistRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> WatchlistResponse:
    try:
        validated = _validate_and_normalize_stock_code(request.stock_code)
        codes = _read_watchlist_codes(service)
        existing_keys = [_watchlist_match_key(c) for c in codes]
        requested_key = _watchlist_match_key(validated)
        if requested_key in existing_keys:
            idx = existing_keys.index(requested_key)
            codes.pop(idx)
            _write_watchlist_codes(service, codes)
        return WatchlistResponse(stock_codes=codes, message=f"{request.stock_code.strip()} 삭제했어요")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"관심종목 삭제 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"관심종목 삭제 실패: {str(e)}"},
        )


@router.get(
    "/{stock_code}/profile",
    response_model=StockProfileResponse,
    responses={
        400: {"description": "股票代码无效", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取个股研究聚合档案",
    description="按独立质量状态聚合行情、历史、研究产物、资讯、持仓关系和监控规则。",
)
def get_stock_profile(
    stock_code: str,
    history_days: int = Query(60, ge=1, le=365, description="日线历史天数"),
) -> StockProfileResponse:
    """Return partial profile data without failing on one optional block."""
    _validate_and_normalize_stock_code(stock_code)
    try:
        return StockProfileResponse(
            **StockProfileService().get_profile(stock_code, history_days=history_days)
        )
    except InvalidStockProfileCode:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_stock_code", "message": "종목 코드와 거래소가 맞지 않아요"},
        )
    except Exception as exc:
        sanitized = sanitize_diagnostic_text(str(exc), max_length=300) or "internal profile error"
        logger.error("종목 리서치 종합 정보 조회 실패: %s", sanitized)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "종목 리서치 종합 정보 조회 실패"},
        )


@router.get(
    "/{stock_code}/quote",
    response_model=StockQuote,
    responses={
        200: {"description": "시세 데이터"},
        404: {"description": "종목 없음", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="종목 실시간 시세 조회",
    description="지정한 종목의 최신 시세 조회"
)
def get_stock_quote(stock_code: str) -> StockQuote:
    """
    종목 실시간 시세 조회
    
    지정한 종목의 최신 시세 조회
    
    Args:
        stock_code: 종목 코드 (예: 600519, 00700, AAPL)
        
    Returns:
        StockQuote: 실시간 시세 데이터
        
    Raises:
        HTTPException: 404 - 종목 없음
    """
    try:
        service = StockService()
        
        # async def 가 아닌 def 를 써서 FastAPI 가 스레드 풀에서 자동 실행
        result = service.get_realtime_quote(stock_code)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"종목 {stock_code} 의 시세 데이터를 찾을 수 없어요"
                }
            )
        
        return StockQuote(
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            current_price=result.get("current_price", 0.0),
            change=result.get("change"),
            change_percent=result.get("change_percent"),
            open=result.get("open"),
            high=result.get("high"),
            low=result.get("low"),
            prev_close=result.get("prev_close"),
            volume=result.get("volume"),
            amount=result.get("amount"),
            update_time=result.get("update_time")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"실시간 시세 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"실시간 시세 조회 실패: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/history",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "과거 시세 데이터"},
        422: {"description": "지원하지 않는 기간 파라미터", "model": ErrorResponse},
        500: {"description": "서버 오류", "model": ErrorResponse},
    },
    summary="종목 과거 시세 조회",
    description="지정한 종목의 과거 캔들(K선) 데이터 조회"
)
def get_stock_history(
    stock_code: str,
    period: str = Query("daily", description="캔들 주기", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365, description="조회 일수")
) -> StockHistoryResponse:
    """
    종목 과거 시세 조회
    
    지정한 종목의 과거 캔들(K선) 데이터 조회
    
    Args:
        stock_code: 종목 코드
        period: 캔들 주기 (daily/weekly/monthly)
        days: 조회 일수
        
    Returns:
        StockHistoryResponse: 과거 시세 데이터
    """
    try:
        service = StockService()
        
        # async def 가 아닌 def 를 써서 FastAPI 가 스레드 풀에서 자동 실행
        result = service.get_history_data(
            stock_code=stock_code,
            period=period,
            days=days
        )
        
        # 응답 모델로 변환
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]
        
        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period=period,
            data=data
        )
    
    except ValueError as e:
        # period 값을 지원하지 않는 경우 (예: weekly/monthly)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_period",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"과거 시세 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"과거 시세 조회 실패: {str(e)}"
            }
        )
