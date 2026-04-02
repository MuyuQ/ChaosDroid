"""诊断规则模型。"""

from typing import Optional

from pydantic import BaseModel, Field

from app.diagnosis.enums import Stage


class DiagnosticRule(BaseModel):
    """诊断规则Pydantic模型。"""

    rule_id: str
    name: str
    priority: int = 50
    enabled: bool = True
    match_all: list[str] = Field(default_factory=list)
    match_any: list[str] = Field(default_factory=list)
    exclude_any: list[str] = Field(default_factory=list)
    match_stage: list[str] = Field(default_factory=list)
    category: str
    root_cause: Optional[str] = None
    base_confidence: float = 0.9
    next_action: Optional[str] = None

    def matches(
        self,
        event_codes: set[str],
        stage: Optional[str] = None,
    ) -> bool:
        """
        检查规则是否匹配给定的事件集合。

        Args:
            event_codes: 标准化代码集合
            stage: 当前阶段

        Returns:
            是否匹配
        """
        # 检查 match_all：所有代码都必须存在
        if self.match_all:
            if not all(code in event_codes for code in self.match_all):
                return False

        # 检查 match_any：至少一个代码存在（如果定义了match_any）
        if self.match_any:
            if not any(code in event_codes for code in self.match_any):
                return False

        # 检查 exclude_any：所有代码都不应该存在
        if self.exclude_any:
            if any(code in event_codes for code in self.exclude_any):
                return False

        # 检查阶段匹配（如果定义了match_stage）
        if self.match_stage and stage:
            if stage.lower() not in [s.lower() for s in self.match_stage]:
                return False

        # 如果没有定义任何匹配条件，默认不匹配
        if not self.match_all and not self.match_any:
            return False

        return True