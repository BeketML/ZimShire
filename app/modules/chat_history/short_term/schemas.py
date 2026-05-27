from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnPair:
    human: str
    assistant: str


@dataclass
class ShortTermContext:
    turn_pairs: list[TurnPair] = field(default_factory=list)

    def format_for_prompt(self) -> str:
        if not self.turn_pairs:
            return "(no prior conversation)"
        lines: list[str] = []
        for pair in self.turn_pairs:
            lines.append(f"User: {pair.human}")
            lines.append(f"Assistant: {pair.assistant}")
        return "\n".join(lines)
