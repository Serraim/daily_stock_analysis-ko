# -*- coding: utf-8 -*-
"""
===================================
포맷팅 유틸리티 모듈
===================================

공통 형식을 플랫폼별 형식으로 바꾸는 각종 포맷팅 함수를 제공합니다.
"""

import re
from typing import Callable, List, Optional

import markdown2

TRUNCATION_SUFFIX = "\n\n...(本段内容过长已截断)"
PAGE_MARKER_PREFIX = f"\n\n📄"
PAGE_MARKER_SAFE_BYTES = 16 # "\n\n📄 9999/9999"
PAGE_MARKER_SAFE_LEN = 13   # "\n\n📄 9999/9999"
MIN_MAX_WORDS = 10
MIN_MAX_BYTES = 40
FENCED_CODE_BLOCK_RE = re.compile(r"(^```[^\n]*\n.*?^```[ \t]*$)", re.MULTILINE | re.DOTALL)
FENCED_CODE_BLOCK_PLACEHOLDER = "@@DSA_FENCED_CODE_BLOCK_{}@@"
HIDDEN_MARKDOWN_METADATA_RE = re.compile(
    r"^\[dsa-[^\]]+\]:\s+#\s+\([^)\n]*\)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Unicode code point ranges for special characters.
_SPECIAL_CHAR_RANGE = (0x10000, 0xFFFFF)
_SPECIAL_CHAR_REGEX = re.compile(r'[\U00010000-\U000FFFFF]')


def _page_marker(i: int, total: int) -> str:
    return f"{PAGE_MARKER_PREFIX} {i+1}/{total}"


def _is_special_char(c: str) -> bool:
    """문자가 특수 문자인지 판별
    
    Args:
        c: 문자
        
    Returns:
        특수 문자면 True, 아니면 False
    """
    if len(c) != 1:
        return False
    cp = ord(c)
    return _SPECIAL_CHAR_RANGE[0] <= cp <= _SPECIAL_CHAR_RANGE[1]


def _count_special_chars(s: str) -> int:
    """
    문자열 안의 특수 문자 개수 계산
    
    Args:
        s: 문자열
    """
    # reg find all (0x10000, 0xFFFFF)
    match = _SPECIAL_CHAR_REGEX.findall(s)
    return len(match)


def _effective_len(s: str, special_char_len: int = 2) -> int:
    """
    문자열의 유효 길이 계산
    
    Args:
        s: 문자열
        special_char_len: 특수 문자 하나의 길이, 기본값 2
        
    Returns:
        s 의 유효 길이
    """
    n = len(s)
    n += _count_special_chars(s) * (special_char_len - 1)
    return n


def _slice_at_effective_len(s: str, effective_len: int, special_char_len: int = 2) -> tuple[str, str]:
    """
    유효 길이 기준으로 문자열 분할
    
    Args:
        s: 문자열
        effective_len: 유효 길이
        special_char_len: 특수 문자 하나의 길이, 기본값 2
        
    Returns:
        분할된 앞부분, 뒷부분 문자열
    """
    if _effective_len(s, special_char_len) <= effective_len:
        return s, ""
    
    s_ = s[:effective_len]
    n_special_chars = _count_special_chars(s_)
    residual_lens = n_special_chars * (special_char_len - 1) + len(s_) - effective_len
    while residual_lens > 0:
        residual_lens -= special_char_len if _is_special_char(s_[-1]) else 1
        s_ = s_[:-1]
    return s_, s[len(s_):]


def markdown_to_html_document(markdown_text: str) -> str:
    """
    Convert Markdown to a complete HTML document (for email, md2img, etc.).

    Uses markdown2 with table and code block support, wraps with inline CSS
    for compact, readable layout. Reused by notification email and md2img.

    Args:
        markdown_text: Raw Markdown content.

    Returns:
        Full HTML document string with DOCTYPE, head, and body.
    """
    html_content = markdown2.markdown(
        markdown_text,
        extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
    )

    css_style = """
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                line-height: 1.5;
                color: #24292e;
                font-size: 14px;
                padding: 15px;
                max-width: 900px;
                margin: 0 auto;
            }
            h1 {
                font-size: 20px;
                border-bottom: 1px solid #eaecef;
                padding-bottom: 0.3em;
                margin-top: 1.2em;
                margin-bottom: 0.8em;
                color: #0366d6;
            }
            h2 {
                font-size: 18px;
                border-bottom: 1px solid #eaecef;
                padding-bottom: 0.3em;
                margin-top: 1.0em;
                margin-bottom: 0.6em;
            }
            h3 {
                font-size: 16px;
                margin-top: 0.8em;
                margin-bottom: 0.4em;
            }
            p {
                margin-top: 0;
                margin-bottom: 8px;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 12px 0;
                display: block;
                overflow-x: auto;
                font-size: 13px;
            }
            th, td {
                border: 1px solid #dfe2e5;
                padding: 6px 10px;
                text-align: left;
            }
            th {
                background-color: #f6f8fa;
                font-weight: 600;
            }
            tr:nth-child(2n) {
                background-color: #f8f8f8;
            }
            tr:hover {
                background-color: #f1f8ff;
            }
            blockquote {
                color: #6a737d;
                border-left: 0.25em solid #dfe2e5;
                padding: 0 1em;
                margin: 0 0 10px 0;
            }
            code {
                padding: 0.2em 0.4em;
                margin: 0;
                font-size: 85%;
                background-color: rgba(27,31,35,0.05);
                border-radius: 3px;
                font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
            }
            pre {
                padding: 12px;
                overflow: auto;
                line-height: 1.45;
                background-color: #f6f8fa;
                border-radius: 3px;
                margin-bottom: 10px;
            }
            hr {
                height: 0.25em;
                padding: 0;
                margin: 16px 0;
                background-color: #e1e4e8;
                border: 0;
            }
            ul, ol {
                padding-left: 20px;
                margin-bottom: 10px;
            }
            li {
                margin: 2px 0;
            }
        """

    return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                {css_style}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """


def markdown_to_plain_text(markdown_text: str) -> str:
    """
    Markdown 을 일반 텍스트로 변환
    
    Markdown 서식 기호를 없애고 읽기 쉽게 유지
    """
    text = markdown_text

    # Markdown reference definitions 제거(예: 숨김 메타데이터 표시)
    text = strip_markdown_reference_definitions(text)
    
    # 제목 기호 # ## ### 제거
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # 굵게 표시 제거 **text** -> text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    
    # 기울임 제거 *text* -> text
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    
    # 인용 제거 > text -> text
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    # 목록 기호 제거 - item -> item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    
    # 구분선 제거 ---
    text = re.sub(r'^---+$', '────────', text, flags=re.MULTILINE)
    
    # 표 문법 제거 |---|---|
    text = re.sub(r'\|[-:]+\|[-:|\s]+\|', '', text)
    text = re.sub(r'^\|(.+)\|$', r'\1', text, flags=re.MULTILINE)
    
    # 불필요한 빈 줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def strip_hidden_markdown_metadata(markdown_text: str) -> str:
    """Strip hidden internal Markdown metadata lines while preserving normal refs."""

    return HIDDEN_MARKDOWN_METADATA_RE.sub("", markdown_text)


def strip_markdown_reference_definitions(markdown_text: str) -> str:
    """Strip Markdown reference-definition lines while preserving the rest."""

    return re.sub(r'^\[[^\]]+\]:\s+.*$', '', markdown_text, flags=re.MULTILINE)


def _bytes(s: str) -> int:
    return len(s.encode('utf-8'))


def utf8_len(s: str) -> int:
    """Return the number of UTF-8 bytes used by ``s``."""

    return len(s.encode("utf-8"))


def utf16_len(s: str) -> int:
    """Return the number of UTF-16 code units used by ``s``.

    Telegram's 4096-character message limit is effectively counted in UTF-16
    units, so astral-plane characters such as emoji consume two units.
    """

    return len(s.encode("utf-16-le")) // 2


def _custom_unit_to_index(text: str, budget: int, len_fn: Callable[[str], int]) -> int:
    """Map a custom-unit budget to the largest safe Python string index."""

    if len_fn(text) <= budget:
        return len(text)
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len_fn(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _has_unclosed_inline_code(text: str) -> bool:
    """Return whether ``text`` ends inside a single-backtick inline code span."""

    escaped = False
    count = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not escaped:
            escaped = True
            i += 1
            continue
        if ch == "`" and not escaped:
            # Triple backticks are handled as fenced code by the caller; skip
            # them here so fence delimiters do not look like inline spans.
            if text[i:i + 3] == "```":
                i += 3
                escaped = False
                continue
            count += 1
        escaped = False
        i += 1
    return count % 2 == 1


def _last_unclosed_markdown_link_start(text: str) -> int:
    """Return the start index of an inline Markdown link split in progress."""

    last_open_paren = text.rfind("](")
    last_close_paren = text.rfind(")")
    if last_open_paren > last_close_paren:
        label_start = text.rfind("[", 0, last_open_paren)
        return label_start if label_start >= 0 else last_open_paren

    last_open_bracket = text.rfind("[")
    last_close_bracket = text.rfind("]")
    if last_open_bracket > last_close_bracket:
        return last_open_bracket

    return -1


def chunk_markdown_preserving_blocks(
    content: str,
    max_units: int,
    *,
    len_fn: Optional[Callable[[str], int]] = None,
    add_page_marker: bool = False,
) -> List[str]:
    """Split Markdown while preserving common formatting boundaries.

    The splitter is intentionally conservative and does not alter report
    semantics.  If a split lands inside a fenced code block, the current chunk is
    closed and the next chunk reopens the same fence language.  It also avoids
    splitting inside inline code spans and Markdown links, and supports custom
    length functions such as :func:`utf16_len`.
    """

    measure = len_fn or len
    if max_units < MIN_MAX_WORDS:
        raise ValueError(f"max_units={max_units} < {MIN_MAX_WORDS}, 무한 재귀에 빠질 수 있습니다.")
    if measure(content) <= max_units:
        return [content]

    marker_reserve = measure(_page_marker(9998, 9998)) if add_page_marker else 0
    indicator_reserve = measure("\n\n(9999/9999)")
    fence_close = "\n```"
    chunks: List[str] = []
    remaining = content
    carry_lang: Optional[str] = None

    while remaining:
        prefix = f"```{carry_lang}\n" if carry_lang is not None else ""
        headroom = max_units - marker_reserve - indicator_reserve - measure(prefix) - measure(fence_close)
        if headroom < MIN_MAX_WORDS:
            headroom = max(MIN_MAX_WORDS, max_units - marker_reserve - indicator_reserve - measure(prefix))
        if headroom <= 0:
            raise ValueError("max_units is too small for markdown-preserving chunking")

        if measure(prefix) + measure(remaining) <= max_units - marker_reserve - indicator_reserve:
            chunks.append(prefix + remaining)
            break

        cp_limit = (
            _custom_unit_to_index(remaining, headroom, measure)
            if measure is not len else min(headroom, len(remaining))
        )
        region = remaining[:cp_limit]
        split_at = region.rfind("\n\n")
        if split_at < cp_limit // 2:
            split_at = region.rfind("\n")
        if split_at < cp_limit // 2:
            split_at = region.rfind(" ")
        if split_at < 1:
            split_at = cp_limit

        candidate = remaining[:split_at]
        unsafe_start = len(candidate)
        if _has_unclosed_inline_code(candidate):
            last_tick = candidate.rfind("`")
            if last_tick >= 0:
                unsafe_start = min(unsafe_start, last_tick)

        link_start = _last_unclosed_markdown_link_start(candidate)
        if link_start >= 0:
            unsafe_start = min(unsafe_start, link_start)

        if unsafe_start < len(candidate):
            safe_split = max(candidate.rfind(" ", 0, unsafe_start), candidate.rfind("\n", 0, unsafe_start))
            if safe_split > 0:
                split_at = safe_split

        chunk_body = remaining[:split_at].rstrip()
        in_code = carry_lang is not None
        lang = carry_lang or ""
        for line in chunk_body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    in_code = False
                    lang = ""
                else:
                    in_code = True
                    tag = stripped[3:].strip()
                    lang = tag.split()[0] if tag else ""

        next_remaining = remaining[split_at:]
        if next_remaining.startswith("\n"):
            next_remaining = next_remaining[1:]
        elif not in_code and next_remaining.startswith(" "):
            line_start = remaining.rfind("\n", 0, split_at) + 1
            if remaining[line_start:split_at].strip(" \t"):
                next_remaining = next_remaining[1:]
        remaining = next_remaining
        full_chunk = prefix + chunk_body

        if in_code:
            full_chunk += fence_close
            carry_lang = lang
        else:
            carry_lang = None

        chunks.append(full_chunk)

    if len(chunks) > 1:
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            suffix = f"\n\n({i + 1}/{total})"
            if add_page_marker:
                suffix += _page_marker(i, total)
            chunks[i] = chunk + suffix
    elif add_page_marker:
        chunks[0] = chunks[0] + _page_marker(0, 1)
    return chunks


def _is_markdown_table_separator(row: str) -> bool:
    return bool(re.match(r'^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$', row))


def _parse_markdown_table_row(row: str) -> List[str]:
    stripped = row.strip()
    if stripped.startswith('|'):
        stripped = stripped[1:]
    if stripped.endswith('|'):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split('|')]


def _strip_inline_markdown(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^\*\*(.+)\*\*$', r'\1', text)
    text = re.sub(r'^\*(.+)\*$', r'\1', text)
    text = text.replace("**", "")
    return text.strip()


def _format_two_column_table_row(header: List[str], row: List[str]) -> str:
    key = _strip_inline_markdown(row[0]) if row else ""
    value = _strip_inline_markdown(row[1]) if len(row) > 1 else ""
    value_header = _strip_inline_markdown(header[1]) if len(header) > 1 else ""

    if not value:
        return key
    if value.upper() == "N/A" and value_header in {"类型", "Type"}:
        return key
    return f"{key}：{value}"


def _flush_table_as_key_value_rows(buffer: List[str], output: List[str], *, bullet: str) -> None:
    if not buffer:
        return

    rows = []
    for raw in buffer:
        if _is_markdown_table_separator(raw):
            continue
        parsed = _parse_markdown_table_row(raw)
        if parsed:
            rows.append(parsed)

    if not rows:
        return

    header = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        if len(header) == 2 and len(row) >= 2:
            output.append(f"{bullet} {_format_two_column_table_row(header, row)}")
            continue

        pairs = []
        for idx, cell in enumerate(row):
            key = _strip_inline_markdown(header[idx]) if idx < len(header) else f"列{idx + 1}"
            pairs.append(f"{key}：{_strip_inline_markdown(cell)}")
        output.append(f"{bullet} {' | '.join(pairs)}")


def _protect_fenced_code_blocks(content: str) -> tuple[str, List[str]]:
    blocks: List[str] = []

    def _replace(match: re.Match) -> str:
        blocks.append(match.group(0))
        return FENCED_CODE_BLOCK_PLACEHOLDER.format(len(blocks) - 1)

    return FENCED_CODE_BLOCK_RE.sub(_replace, content), blocks


def _restore_fenced_code_blocks(content: str, blocks: List[str]) -> str:
    restored = content
    for idx, block in enumerate(blocks):
        restored = restored.replace(FENCED_CODE_BLOCK_PLACEHOLDER.format(idx), block)
    return restored


def _transform_outside_fenced_code_blocks(content: str, transform: Callable[[str], str]) -> str:
    protected, blocks = _protect_fenced_code_blocks(content)
    return _restore_fenced_code_blocks(transform(protected), blocks)


def _markdown_tables_to_key_value_rows_unprotected(content: str, *, bullet: str) -> str:
    """Convert pipe tables to compact key-value rows for chat clients."""

    lines: List[str] = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith('|'):
            table_buffer.append(line)
            continue

        if table_buffer:
            _flush_table_as_key_value_rows(table_buffer, lines, bullet=bullet)
            table_buffer = []

        lines.append(line)

    if table_buffer:
        _flush_table_as_key_value_rows(table_buffer, lines, bullet=bullet)

    return "\n".join(lines).strip()


def markdown_tables_to_key_value_rows(content: str, *, bullet: str = "•") -> str:
    """Convert pipe tables to compact key-value rows outside fenced code blocks."""

    return _transform_outside_fenced_code_blocks(
        content,
        lambda text: _markdown_tables_to_key_value_rows_unprotected(text, bullet=bullet),
    ).strip()


def _chunk_by_max_bytes(content: str, max_bytes: int) -> List[str]:
    if _bytes(content) <= max_bytes:
        return [content]
    if max_bytes < MIN_MAX_BYTES:
        raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}, 무한 재귀에 빠질 수 있습니다.")
    
    sections: List[str] = []
    suffix = TRUNCATION_SUFFIX
    effective_max_bytes = max_bytes - _bytes(suffix)
    if effective_max_bytes <= 0:
        effective_max_bytes = max_bytes
        suffix = ""
        
    while True:
        chunk, content = slice_at_max_bytes(content, effective_max_bytes)
        if content.strip() != "":
            sections.append(chunk + suffix)
        else:
            # 마지막 조각이므로 바로 추가하고 루프 종료
            sections.append(chunk)
            break
    return sections


def chunk_content_by_max_bytes(content: str, max_bytes: int, add_page_marker: bool = False) -> List[str]:
    """
    바이트 수 기준으로 메시지를 똑똑하게 분할
    
    Args:
        content: 전체 메시지 내용
        max_bytes: 메시지 1건의 최대 바이트 수
        add_page_marker: 페이지 표시를 붙일지 여부
        
    Returns:
        분할된 블록 목록
    """
    def _chunk(content: str, max_bytes: int) -> List[str]:
        # 구분선/제목 기준 분할을 우선해 페이지가 자연스럽게 나뉘도록 함
        if max_bytes < MIN_MAX_BYTES:
            raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}, 무한 재귀에 빠질 수 있습니다.")
        
        if _bytes(content) <= max_bytes:
            return [content]
        
        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            # 똑똑하게 나눌 수 없으면 글자 수 기준으로 강제 분할
            return _chunk_by_max_bytes(content, max_bytes)
        
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_bytes = 0
        separator_bytes = _bytes(separator) if separator else 0
        effective_max_bytes = max_bytes - separator_bytes

        for section in sections:
            section += separator
            section_bytes = _bytes(section)
            
            # section 하나만으로도 너무 길면 강제로 잘라야 함
            if section_bytes > effective_max_bytes:
                # 지금까지 모은 내용을 먼저 저장
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_bytes = 0

                # 바이트 기준으로 강제로 잘라 단락 전체가 사라지는 것을 막음
                section_chunks = _chunk(
                    section[:-separator_bytes], effective_max_bytes
                )
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue

            # 추가한 뒤 길이 초과인지 확인
            if current_bytes + section_bytes > effective_max_bytes:
                # 현재 블록을 저장하고 새 블록 시작
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes
                
        # 마지막 블록 추가
        if current_chunk:
            chunks.append("".join(current_chunk))
            
        # 마지막 블록의 구분자 제거
        if (chunks and 
            len(chunks[-1]) > separator_bytes and 
            chunks[-1][-separator_bytes:] == separator
        ):
            chunks[-1] = chunks[-1][:-separator_bytes]
        
        return chunks
    
    if add_page_marker:
        max_bytes = max_bytes - PAGE_MARKER_SAFE_BYTES
    
    chunks = _chunk(content, max_bytes)
    if add_page_marker:
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total_chunks)
    return chunks


def slice_at_max_bytes(text: str, max_bytes: int) -> tuple[str, str]:
    """
    바이트 수 기준으로 문자열을 자르되, 멀티바이트 문자 중간에서 잘리지 않게 함

    Args:
        text: 자를 문자열
        max_bytes: 최대 바이트 수

    Returns:
        (잘린 문자열, 잘리지 않고 남은 내용)
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, ""

    # 최대 바이트 위치부터 앞으로 거슬러 올라가며 완전한 UTF-8 문자 경계를 찾음
    truncated = encoded[:max_bytes]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]

    truncated = truncated.decode('utf-8', errors='ignore')
    return truncated, text[len(truncated):]


def _format_feishu_markdown_unprotected(content: str) -> str:
    lines = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # 표 행 처리
        if line.strip().startswith('|'):
            table_buffer.append(line)
            continue

        # 표 버퍼 비우기
        if table_buffer:
            _flush_table_as_key_value_rows(table_buffer, lines, bullet="•")
            table_buffer = []

        # 제목 변환(# ## ### 등)
        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip()
            line = f"**{title}**" if title else ""
        # 인용 블록 변환
        elif line.startswith('> '):
            quote = line[2:].strip()
            line = quote
        # 구분선 변환
        elif line.strip() == '---':
            line = '────────'
        # 목록 항목 변환
        elif line.startswith('- '):
            line = f"• {line[2:].strip()}"

        lines.append(line)

    # 끝에 남은 표 처리
    if table_buffer:
        _flush_table_as_key_value_rows(table_buffer, lines, bullet="•")

    return "\n".join(lines).strip()


def format_feishu_markdown(content: str) -> str:
    """
    일반 Markdown 을 Feishu lark_md 에 더 잘 맞는 형식으로 변환

    변환 규칙:
    - Feishu 는 Markdown 제목(# / ## / ###)을 지원하지 않아 굵게 표시로 대체
    - 인용 블록은 접두어로 대체
    - 구분선은 가는 선으로 통일
    - 표는 항목 목록으로 변환

    Args:
        content: 원본 Markdown 내용

    Returns:
        변환된 Feishu Markdown 형식 내용

    Example:
        >>> markdown = "# 标题\\n> 引用\\n| 列1 | 列2 |"
        >>> formatted = format_feishu_markdown(markdown)
        >>> print(formatted)
        **标题**
        💬 引用
        • 列1：值1 | 列2：值2
    """
    def _flush_table_rows(buffer: List[str], output: List[str]) -> None:
        """표 버퍼의 행을 Feishu 형식으로 변환"""
        if not buffer:
            return

        def _parse_row(row: str) -> List[str]:
            """표 행을 파싱해 셀 추출"""
            return _parse_markdown_table_row(row)

        rows = []
        for raw in buffer:
            # 구분 행 건너뛰기(예: |---|---|)
            if re.match(r'^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$', raw):
                continue
            parsed = _parse_row(raw)
            if parsed:
                rows.append(parsed)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"列{idx + 1}"
                pairs.append(f"{key}：{cell}")
            output.append(f"• {' | '.join(pairs)}")

    lines = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # 표 행 처리
        if line.strip().startswith('|'):
            table_buffer.append(line)
            continue

        # 표 버퍼 비우기
        if table_buffer:
            _flush_table_rows(table_buffer, lines)
            table_buffer = []

        # 제목 변환(# ## ### 등)
        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip()
            line = f"**{title}**" if title else ""
        # 인용 블록 변환
        elif line.startswith('> '):
            quote = line[2:].strip()
            line = f"💬 {quote}" if quote else ""
        # 구분선 변환
        elif line.strip() == '---':
            line = '────────'
        # 목록 항목 변환
        elif line.startswith('- '):
            line = f"• {line[2:].strip()}"

        lines.append(line)

    # 끝에 남은 표 처리
    if table_buffer:
        _flush_table_rows(table_buffer, lines)

    return "\n".join(lines).strip()


def _format_telegram_markdown_unprotected(content: str) -> str:
    """Convert common report Markdown to Telegram legacy Markdown."""

    result = _markdown_tables_to_key_value_rows_unprotected(content, bullet="-")
    result = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', result, flags=re.MULTILINE)
    result = re.sub(r'\*\*(.+?)\*\*', r'*\1*', result)
    result = re.sub(r'^\s*---+\s*$', '────────', result, flags=re.MULTILINE)
    result = _escape_telegram_non_link_markdown_chars(result)
    return result.strip()


def _escape_telegram_non_link_markdown_chars(content: str) -> str:
    """Escape Telegram Markdown link metacharacters outside valid links."""

    links: list[str] = []

    def _save_link(match: re.Match) -> str:
        links.append(match.group(0))
        return f"@@DSA_TELEGRAM_LINK_{len(links) - 1}@@"

    result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _save_link, content)
    for char in ("[", "]", "(", ")"):
        result = result.replace(char, f"\\{char}")

    for index, link in enumerate(links):
        result = result.replace(f"@@DSA_TELEGRAM_LINK_{index}@@", link)
    return result


def format_telegram_markdown(content: str) -> str:
    """Convert common report Markdown to Telegram legacy Markdown."""

    return _transform_outside_fenced_code_blocks(
        content,
        _format_telegram_markdown_unprotected,
    ).strip()


def format_wechat_markdown(content: str) -> str:
    """Keep WeChat Markdown style while making pipe tables mobile-readable."""

    result = markdown_tables_to_key_value_rows(content, bullet="•")
    result = re.sub(r'^\s*---+\s*$', '────────', result, flags=re.MULTILINE)
    return result.strip()


def _format_slack_mrkdwn_unprotected(content: str) -> str:
    """Convert common report Markdown to Slack mrkdwn."""

    result = _markdown_tables_to_key_value_rows_unprotected(content, bullet="•")
    result = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<\2|\1>', result)
    result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', result)
    result = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', result, flags=re.MULTILINE)
    result = re.sub(r'\*\*(.+?)\*\*', r'*\1*', result)
    result = re.sub(r'^\s*---+\s*$', '────────', result, flags=re.MULTILINE)
    return result.strip()


def format_slack_mrkdwn(content: str) -> str:
    """Convert common report Markdown to Slack mrkdwn."""

    return _transform_outside_fenced_code_blocks(
        content,
        _format_slack_mrkdwn_unprotected,
    ).strip()


def _chunk_by_separators(content: str) -> tuple[list[str], str]:
    """
    구분선 같은 특수 문자를 기준으로 메시지를 여러 블록으로 분할
    
    Args:
        content: 전체 메시지 내용
        
    Returns:
        sections: 분할된 블록 목록
        separator: 블록 사이 구분자, None 이면 분할 불가
    """
    # 스마트 분할: "---"(종목 사이 구분선) 기준을 우선
    # 그다음 각 단계 제목 기준 분할 시도
    if "\n---\n" in content:
        sections = content.split("\n---\n")
        separator = "\n---\n"
    elif "\n# " in content:
        # # 기준 분할 (1단계 제목 호환)
        parts = content.split("\n# ")
        sections = [parts[0]] + [f"# {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n## " in content:
        # ## 기준 분할 (2단계 제목 호환)
        parts = content.split("\n## ")
        sections = [parts[0]] + [f"## {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n### " in content:
        # ### 기준 분할
        parts = content.split("\n### ")
        sections = [parts[0]] + [f"### {p}" for p in parts[1:]]
        separator = "\n"
    elif "\n**" in content:
        # ** 굵은 제목 기준 분할 (AI 가 표준 Markdown 제목을 출력하지 않은 경우 대응)
        parts = content.split("\n**")
        sections = [parts[0]] + [f"**{p}" for p in parts[1:]]
        separator = "\n"
    elif "\n" in content:
        # \n 기준 분할
        sections = content.split("\n")
        separator = "\n"
    else:
        return [content], ""
    return sections, separator


def _chunk_by_max_words(content: str, max_words: int, special_char_len: int = 2) -> list[str]:
    """
    글자 수 기준으로 메시지 분할
    
    Args:
        content: 전체 메시지 내용
        max_words: 메시지 1건의 최대 글자 수
        special_char_len: 특수 문자 하나의 길이, 기본값 2
        
    Returns:
        분할된 블록 목록
    """
    if _effective_len(content, special_char_len) <= max_words:
        return [content]
    if max_words < MIN_MAX_WORDS:
        raise ValueError(
            f"max_words={max_words} < {MIN_MAX_WORDS}, 무한 재귀에 빠질 수 있습니다."
        )

    sections = []
    suffix = TRUNCATION_SUFFIX
    effective_max_words = max_words - len(suffix)  # 접미어 길이를 미리 빼서 경계 초과 방지
    if effective_max_words <= 0:
        effective_max_words = max_words
        suffix = ""

    while True:
        chunk, content = _slice_at_effective_len(content, effective_max_words, special_char_len)
        if content.strip() != "":
            sections.append(chunk + suffix)
        else:
            # 마지막 조각이므로 바로 추가하고 루프 종료
            sections.append(chunk)
            break
    return sections


def chunk_content_by_max_words(
    content: str, 
    max_words: int, 
    special_char_len: int = 2,
    add_page_marker: bool = False
    ) -> list[str]:
    """
    글자 수 기준으로 메시지를 똑똑하게 분할
    
    Args:
        content: 전체 메시지 내용
        max_words: 메시지 1건의 최대 글자 수
        special_char_len: 특수 문자 하나의 길이, 기본값 2
        add_page_marker: 페이지 표시를 붙일지 여부
        
    Returns:
        분할된 블록 목록
    """
    def _chunk(content: str, max_words: int, special_char_len: int = 2) -> list[str]:
        if max_words < MIN_MAX_WORDS:
            # Safe guard, 무한 재귀 방지
            # 이론상 max_words 는 재귀할 때마다 한없이 작아질 수 있지만 실제로는 거의 일어나지 않음.
            # _chunk_by_separators 가 매번 구분자를 반환하고 max_words 초기값이 너무 작은 경우에만 발생.
            raise ValueError(f"max_words={max_words} < {MIN_MAX_WORDS}, 무한 재귀에 빠질 수 있습니다.")
        
        if _effective_len(content, special_char_len) <= max_words:
            return [content]

        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            # 똑똑하게 나눌 수 없으면 글자 수 기준으로 강제 분할
            return _chunk_by_max_words(content, max_words, special_char_len)

        chunks = []
        current_chunk = []
        current_word_len = 0
        separator_len = len(separator) if separator else 0
        effective_max_words = max_words - separator_len # 구분자 길이를 미리 빼서 경계 초과 방지

        for section in sections:
            section += separator
            section_word_len = _effective_len(section, special_char_len)

            # section 하나만으로도 너무 길면 강제로 잘라야 함
            if section_word_len > max_words:
                # 지금까지 모은 내용을 먼저 저장
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_word_len = 0

                # 너무 긴 이 section 을 강제로 자름
                section_chunks = _chunk(
                    section[:-separator_len], effective_max_words, special_char_len
                    )
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue

            # 추가한 뒤 길이 초과인지 확인
            if current_word_len + section_word_len > max_words:
                # 현재 블록을 저장하고 새 블록 시작
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_word_len = section_word_len
            else:
                current_chunk.append(section)
                current_word_len += section_word_len

        # 마지막 블록 추가
        if current_chunk:
            chunks.append("".join(current_chunk))

        # 마지막 블록의 구분자 제거
        if (chunks and
            len(chunks[-1]) > separator_len and
            chunks[-1][-separator_len:] == separator
        ):
            chunks[-1] = chunks[-1][:-separator_len]
        return chunks
    
    
    if add_page_marker:
        max_words = max_words - PAGE_MARKER_SAFE_LEN
    
    chunks = _chunk(content, max_words, special_char_len)
    if add_page_marker:
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total_chunks)
    return chunks
