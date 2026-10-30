import hashlib
import random
import secrets
import threading
import time
import requests
import json
import uuid
import logging
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

original_request = requests.Session.request

ua = UserAgent()


class AuthCache:
    def __init__(self):
        self.data = None
        self.expire_at = 0
        self.lock = threading.Lock()
        self.ttl = 20


_cache = AuthCache()


class PatchSign:
    def __init__(self):
        self.patched = False

    def set_patch(self, patched):
        self.patched = patched

    def is_patched(self):
        return self.patched


_patch_sign = PatchSign()


def _get_nid(user_agent):
    """
    Eastmoney(동방재부)의 NID 인증 토큰 가져오기

    Args:
        user_agent (str): 다른 브라우저 접속처럼 보이게 할 User-Agent 문자열

    Returns:
        str: 받아 온 NID 인증 토큰, 실패하면 None

    설명:
        Eastmoney 인증 API 에 요청을 보내 NID 토큰을 받아 오며,
        이후 데이터 접근 인증에 쓴다. 너무 잦은 요청을 막기 위해 캐시를 사용한다.
    """
    now = time.time()
    # 캐시가 아직 유효한지 확인 (중복 요청 방지)
    if _cache.data and now < _cache.expire_at:
        return _cache.data
    # 스레드 락으로 동시 실행 안전 확보
    with _cache.lock:
        try:
            def generate_uuid_md5():
                """
                UUID 를 만들고 MD5 해시 처리
                :return: MD5 해시값 (32자리 16진수 문자열)
                """
                # UUID 생성
                unique_id = str(uuid.uuid4())
                # UUID 를 MD5 로 해시
                md5_hash = hashlib.md5(unique_id.encode('utf-8')).hexdigest()
                return md5_hash

            def generate_st_nvi():
                """
                st_nvi 값을 만드는 함수
                :return: 만들어진 st_nvi 값
                """
                HASH_LENGTH = 4  # 해시값 앞부분 몇 자리만 사용

                def generate_random_string(length=21):
                    """
                    지정한 길이의 무작위 문자열 생성
                    :param length: 문자열 길이, 기본값 21
                    :return: 무작위 문자열
                    """
                    charset = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"
                    return ''.join(secrets.choice(charset) for _ in range(length))

                def sha256(input_str):
                    """
                    SHA-256 해시값 계산
                    :param input_str: 입력 문자열
                    :return: 해시값 (16진수)
                    """
                    return hashlib.sha256(input_str.encode('utf-8')).hexdigest()

                random_str = generate_random_string()
                hash_prefix = sha256(random_str)[:HASH_LENGTH]
                return random_str + hash_prefix

            url = "https://anonflow2.eastmoney.com/backend/api/webreport"
            # 화면 해상도를 무작위로 골라 실제 브라우저 요청처럼 보이게 함
            screen_resolution = random.choice(['1920X1080', '2560X1440', '3840X2160'])
            payload = json.dumps({
                "osPlatform": "Windows",
                "sourceType": "WEB",
                "osversion": "Windows 10.0",
                "language": "zh-CN",
                "timezone": "Asia/Shanghai",
                "webDeviceInfo": {
                    "screenResolution": screen_resolution,
                    "userAgent": user_agent,
                    "canvasKey": generate_uuid_md5(),
                    "webglKey": generate_uuid_md5(),
                    "fontKey": generate_uuid_md5(),
                    "audioKey": generate_uuid_md5()
                }
            })
            headers = {
                'Cookie': f'st_nvi={generate_st_nvi()}',
                'Content-Type': 'application/json'
            }
            # 무한 대기를 막기 위해 타임아웃 설정
            response = requests.request("POST", url, headers=headers, data=payload, timeout=30)
            response.raise_for_status()  # 4xx/5xx 응답이면 HTTPError 발생

            data = response.json()
            nid = data['data']['nid']

            _cache.data = nid
            _cache.expire_at = now + _cache.ttl
            return nid
        except requests.exceptions.RequestException as e:
            logger.warning(f"Eastmoney 인증 API 요청 실패: {e}")
            _cache.data = None
            # 이 API 가 실패하면 방식 자체가 막혔을 가능성이 커서 이후에도 계속 실패하기 쉽다. 토큰을 못 받으면 다음에 또 요청하므로, 만료 시간을 길게 잡아 잦은 요청을 피한다
            _cache.expire_at = now + 5 * 60
            return None
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Eastmoney 인증 API 응답 해석 실패: {e}")
            _cache.data = None
            # 이 API 가 실패하면 방식 자체가 막혔을 가능성이 커서 이후에도 계속 실패하기 쉽다. 토큰을 못 받으면 다음에 또 요청하므로, 만료 시간을 길게 잡아 잦은 요청을 피한다
            _cache.expire_at = now + 5 * 60
            return None


def eastmoney_patch():
    if _patch_sign.is_patched():
        return

    def patched_request(self, method, url, **kwargs):
        # 대상이 아닌 도메인은 제외
        is_target = any(
            d in (url or "")
            for d in [
                "fund.eastmoney.com",
                "push2.eastmoney.com",
                "push2his.eastmoney.com",
            ]
        )
        if not is_target:
            return original_request(self, method, url, **kwargs)
        # 무작위 User-Agent 하나 가져오기
        user_agent = ua.random
        # Headers 처리: 호출한 코드가 넘긴 headers 를 망가뜨리지 않도록 함
        headers = kwargs.get("headers", {})
        headers["User-Agent"] = user_agent
        nid = _get_nid(user_agent)
        if nid:
            headers["Cookie"] = f"nid18={nid}"
        kwargs["headers"] = headers
        # 무작위로 잠깐 쉬어 차단 위험 줄이기
        sleep_time = random.uniform(1, 4)
        time.sleep(sleep_time)
        return original_request(self, method, url, **kwargs)

    # Session 의 request 진입점을 전역으로 교체
    requests.Session.request = patched_request
    _patch_sign.set_patch(True)
