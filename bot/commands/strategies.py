# -*- coding: utf-8 -*-
"""
Strategies / Skills listing command.

Shows all available trading strategies and their activation status.
"""

import logging
from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class StrategiesCommand(BotCommand):
    """
    List available trading strategies.

    Usage:
        /strategies         - List all strategies
        /strategies active  - Show only active strategies
    """

    @property
    def name(self) -> str:
        return "strategies"

    @property
    def aliases(self) -> List[str]:
        return ["skills", "策略", "策略列表"]

    @property
    def description(self) -> str:
        return "사용 가능한 매매 전략 보기"

    @property
    def usage(self) -> str:
        return "/strategies [active]"

    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute the strategies list command."""
        show_active_only = bool(args and args[0].lower() in ("active", "激活", "已激活"))

        try:
            from src.agent.factory import get_skill_manager
            from src.config import get_config

            config = get_config()
            sm = get_skill_manager(config)
            from src.agent.factory import DEFAULT_AGENT_SKILLS

            # Derive activation status from config without mutating the skill
            # manager — this is a read-only listing command.
            configured_active: set = set(config.agent_skills or DEFAULT_AGENT_SKILLS)

            all_skills = sm.list_skills()
            if not all_skills:
                return BotResponse.text_response("📋 사용 가능한 전략이 없습니다. strategies/ 폴더를 확인해 주세요.")

            skills = all_skills
            if show_active_only:
                skills = [s for s in all_skills if s.name in configured_active]
                if not skills:
                    return BotResponse.text_response("📋 현재 켜진 전략이 없습니다.")

            # Group by category
            categories = {"trend": "📈 추세형", "pattern": "📊 패턴형", "reversal": "🔄 반전형", "framework": "🧩 프레임워크형"}
            grouped = {}
            for skill in skills:
                cat = skill.category or "trend"
                grouped.setdefault(cat, []).append(skill)

            lines = ["📋 **매매 전략 목록**", ""]

            ordered_keys = ["trend", "pattern", "reversal", "framework"]
            for cat_key in ordered_keys + [k for k in grouped if k not in ordered_keys]:
                cat_skills = grouped.get(cat_key)
                if not cat_skills:
                    continue
                cat_label = categories.get(cat_key, f"📌 {cat_key}")
                lines.append(f"**{cat_label}**")
                for s in cat_skills:
                    status = "✅" if s.name in configured_active else "⬜"
                    source_tag = ""
                    if s.source and s.source != "builtin":
                        source_tag = " (사용자 정의)"
                    lines.append(f"  {status} `{s.name}` — {s.display_name}{source_tag}")
                    lines.append(f"      {s.description}")
                lines.append("")

            active_count = sum(1 for s in all_skills if s.name in configured_active)
            total_count = len(all_skills)
            lines.append(f"전략 {total_count}개 중 {active_count}개 켜짐")
            lines.append(f"\n💡 `/ask <종목코드> <전략이름>`으로 전략을 골라 분석할 수 있습니다")

            return BotResponse.markdown_response("\n".join(lines))

        except Exception as e:
            logger.error(f"Strategies command failed: {e}")
            logger.exception("Strategies error details:")
            return BotResponse.text_response(f"⚠️ 전략 목록을 가져오지 못했습니다: {str(e)}")
