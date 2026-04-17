"""Shared interfaces for exploration policies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class PolicyInput:
    """Minimal state exposed to exploration policies at each step."""

    step_index: int
    max_steps: int
    action_space: Sequence[str]
    position: Sequence[float]
    rotation_wxyz: Sequence[float]
    last_action: Optional[str] = None
    last_action_collided: bool = False
    task: Optional[Mapping[str, Any]] = None
    occupancy_summary: Optional[Mapping[str, Any]] = None
    object_memory_summary: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class PolicyDecision:
    """Structured action selection returned by a policy."""

    action: str
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class BaseExplorationPolicy(ABC):
    """Common interface that random/frontier/task-aware policies will share."""

    name: str = "base"

    @abstractmethod
    def reset(
        self,
        *,
        action_space: Sequence[str],
        task: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Prepare policy state for a new episode."""

    @abstractmethod
    def act(self, policy_input: PolicyInput) -> PolicyDecision:
        """Select the next action for the current exploration step."""

    def config_dict(self) -> dict[str, Any]:
        config = getattr(self, "config", None)
        if config is None:
            return {}
        if hasattr(config, "__dataclass_fields__"):
            return asdict(config)
        return dict(config)
