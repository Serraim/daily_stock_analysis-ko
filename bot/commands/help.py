# -*- coding: utf-8 -*-
"""
===================================
도움말 명령
===================================

사용 가능한 명령 목록과 사용법을 보여줍니다.
"""

from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse


class HelpCommand(BotCommand):
    """
    도움말 명령
    
    사용 가능한 모든 명령의 목록과 사용법을 보여줍니다.
    특정 명령의 자세한 도움말도 볼 수 있습니다.
    
    사용법:
        /help         - 모든 명령 보기
        /help analyze - analyze 명령 자세한 도움말 보기
    """
    
    @property
    def name(self) -> str:
        return "help"
    
    @property
    def aliases(self) -> List[str]:
        return ["h", "帮助", "?"]
    
    @property
    def description(self) -> str:
        return "도움말 보기"
    
    @property
    def usage(self) -> str:
        return "/help [명령이름]"
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """도움말 명령 실행"""
        # 순환 import를 피하려고 늦게 import
        from bot.dispatcher import get_dispatcher
        
        dispatcher = get_dispatcher()
        
        # 명령 이름을 주면 그 명령의 자세한 도움말을 보여줌
        if args:
            cmd_name = args[0]
            command = dispatcher.get_command(cmd_name)
            
            if command is None:
                return BotResponse.error_response(f"알 수 없는 명령: {cmd_name}")
            
            # 자세한 도움말 만들기
            help_text = self._format_command_help(command, dispatcher.command_prefix)
            return BotResponse.markdown_response(help_text)
        
        # 전체 명령 목록 보여주기
        commands = dispatcher.list_commands(include_hidden=False)
        prefix = dispatcher.command_prefix
        
        help_text = self._format_help_list(commands, prefix)
        return BotResponse.markdown_response(help_text)
    
    def _format_help_list(self, commands: List[BotCommand], prefix: str) -> str:
        """명령 목록 서식 만들기"""
        lines = [
            "📚 **주식 분석 도우미 - 명령 도움말**",
            "",
            "사용 가능한 명령:",
            "",
        ]
        
        for cmd in commands:
            # 명령 이름과 별칭
            aliases_str = ""
            if cmd.aliases:
                # 중국어 별칭은 빼고 영어 별칭만 표시
                en_aliases = [a for a in cmd.aliases if a.isascii()]
                if en_aliases:
                    aliases_str = f" ({', '.join(prefix + a for a in en_aliases[:2])})"
            
            lines.append(f"• {prefix}{cmd.name}{aliases_str} - {cmd.description}")
            lines.append("")

        lines.extend([
            "",
            "---",
            f"💡 {prefix}help <명령이름>을 입력하면 자세한 사용법을 볼 수 있습니다",
            "",
            "**예시:**",
            "",
            f"• {prefix}analyze 301023 - 奕帆传动",
            "",
            f"• {prefix}market - 시장 전체 복기 보기",
            "",
            f"• {prefix}batch - 관심 종목 일괄 분석",
        ])
        
        return "\n".join(lines)
    
    def _format_command_help(self, command: BotCommand, prefix: str) -> str:
        """명령 하나의 자세한 도움말 서식 만들기"""
        lines = [
            f"📖 **{prefix}{command.name}** - {command.description}",
            "",
            f"**사용법:** `{command.usage}`",
            "",
        ]
        
        # 별칭
        if command.aliases:
            aliases = [f"`{prefix}{a}`" if a.isascii() else f"`{a}`" for a in command.aliases]
            lines.append(f"**별칭:** {', '.join(aliases)}")
            lines.append("")
        
        # 권한
        if command.admin_only:
            lines.append("⚠️ **관리자 권한 필요**")
            lines.append("")
        
        return "\n".join(lines)
