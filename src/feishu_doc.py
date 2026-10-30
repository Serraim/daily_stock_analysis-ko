# feishu_doc.py
# -*- coding: utf-8 -*-
import logging
import json
import lark_oapi as lark
from lark_oapi.api.docx.v1 import *
from typing import List, Dict, Any, Optional
from src.config import get_config

logger = logging.getLogger(__name__)


class FeishuDocManager:
    """Feishu(Lark) 클라우드 문서 관리자 (공식 SDK lark-oapi 기반)"""

    def __init__(self):
        self.config = get_config()
        self.app_id = self.config.feishu_app_id
        self.app_secret = self.config.feishu_app_secret
        self.folder_token = self.config.feishu_folder_token

        # SDK 클라이언트 초기화
        # tenant_access_token 발급과 갱신은 SDK 가 알아서 처리하므로 손댈 필요 없음
        if self.is_configured():
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()
        else:
            self.client = None

    def is_configured(self) -> bool:
        """설정이 빠짐없이 되어 있는지 확인"""
        return bool(self.app_id and self.app_secret and self.folder_token)

    def create_daily_doc(self, title: str, content_md: str) -> Optional[str]:
        """
        일일 리포트 문서 생성
        """
        if not self.client or not self.is_configured():
            logger.warning("Feishu SDK 가 초기화되지 않았거나 설정이 빠짐, 문서 생성 건너뜀")
            return None

        try:
            # 1. 문서 생성
            # 공식 SDK 의 Builder 패턴으로 요청 구성
            create_request = CreateDocumentRequest.builder() \
                .request_body(CreateDocumentRequestBody.builder()
                              .folder_token(self.folder_token)
                              .title(title)
                              .build()) \
                .build()

            response = self.client.docx.v1.document.create(create_request)

            if not response.success():
                logger.error(f"문서 생성 실패: {response.code} - {response.msg} - {response.error}")
                return None

            doc_id = response.data.document.document_id
            # 여기 domain 은 링크를 만들기 위한 것일 뿐, 실제 접속 시 리다이렉트됨
            doc_url = f"https://feishu.cn/docx/{doc_id}"
            logger.info(f"Feishu 문서 생성 완료: {title} (ID: {doc_id})")

            # 2. Markdown 을 해석해 내용 쓰기
            # Markdown 을 SDK 가 요구하는 Block 객체 목록으로 변환
            blocks = self._markdown_to_sdk_blocks(content_md)

            # Feishu API 는 한 번에 쓸 수 있는 Block 수가 제한되므로 (약 50개 권장) 나눠서 씀
            batch_size = 50
            doc_block_id = doc_id  # 문서 자체도 하나의 block

            for i in range(0, len(blocks), batch_size):
                batch_blocks = blocks[i:i + batch_size]

                # 블록 일괄 추가 요청 구성
                batch_add_request = CreateDocumentBlockChildrenRequest.builder() \
                    .document_id(doc_id) \
                    .block_id(doc_block_id) \
                    .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                                  .children(batch_blocks)  # SDK 는 Block 객체 목록이 필요
                                  .index(-1)  # 맨 끝에 추가
                                  .build()) \
                    .build()

                write_resp = self.client.docx.v1.document_block_children.create(batch_add_request)

                if not write_resp.success():
                    logger.error(f"문서 내용 쓰기 실패(배치 {i}): {write_resp.code} - {write_resp.msg}")

            logger.info(f"문서 내용 쓰기 완료")
            return doc_url

        except Exception as e:
            logger.error(f"Feishu 문서 작업 중 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _markdown_to_sdk_blocks(self, md_text: str) -> List[Block]:
        """
        간단한 Markdown 을 Feishu SDK 의 Block 객체로 변환
        """
        blocks = []
        lines = md_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 기본은 일반 텍스트 (Text = 2)
            block_type = 2
            text_content = line

            # 제목 인식
            if line.startswith('# '):
                block_type = 3  # H1
                text_content = line[2:]
            elif line.startswith('## '):
                block_type = 4  # H2
                text_content = line[3:]
            elif line.startswith('### '):
                block_type = 5  # H3
                text_content = line[4:]
            elif line.startswith('---'):
                # 구분선
                blocks.append(Block.builder()
                              .block_type(22)
                              .divider(Divider.builder().build())
                              .build())
                continue

            # Text 유형 Block 구성
            # SDK 구조는 중첩이 깊음: Block -> Text -> elements -> TextElement -> TextRun -> content
            text_run = TextRun.builder() \
                .content(text_content) \
                .text_element_style(TextElementStyle.builder().build()) \
                .build()

            text_element = TextElement.builder() \
                .text_run(text_run) \
                .build()

            text_obj = Text.builder() \
                .elements([text_element]) \
                .style(TextStyle.builder().build()) \
                .build()

            # block_type 에 맞는 속성 컨테이너에 넣기
            block_builder = Block.builder().block_type(block_type)

            if block_type == 2:
                block_builder.text(text_obj)
            elif block_type == 3:
                block_builder.heading1(text_obj)
            elif block_type == 4:
                block_builder.heading2(text_obj)
            elif block_type == 5:
                block_builder.heading3(text_obj)

            blocks.append(block_builder.build())

        return blocks