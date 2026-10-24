"""Usage ledger for optional model calls.

This foundation run does not call a model. The ledger stays at zero until a
later phase records a real call. Do not invent token counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCall:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float


@dataclass
class UsageLedger:
    calls: list[ModelCall] = field(default_factory=list)

    def record(self, call: ModelCall) -> None:
        self.calls.append(call)

    def summary(self) -> dict[str, float | int]:
        return {
            "model_calls": len(self.calls),
            "input_tokens": sum(call.input_tokens for call in self.calls),
            "output_tokens": sum(call.output_tokens for call in self.calls),
            "estimated_cost": sum(call.estimated_cost for call in self.calls),
        }
