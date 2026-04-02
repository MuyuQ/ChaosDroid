"""规则YAML加载器。"""

from pathlib import Path
from typing import Optional

import yaml

from app.diagnosis.config import settings
from app.diagnosis.engine.rule import DiagnosticRule


class RuleLoader:
    """规则加载器。"""

    def __init__(self, rules_path: Optional[Path] = None):
        """
        初始化规则加载器。

        Args:
            rules_path: 规则文件目录路径
        """
        self.rules_path = rules_path or settings.rules_path

    def load_rules(self, file_name: str = "core_rules.yaml") -> list[DiagnosticRule]:
        """
        从YAML文件加载规则。

        Args:
            file_name: 规则文件名

        Returns:
            规则列表
        """
        file_path = self.rules_path / file_name

        if not file_path.exists():
            return []

        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "rules" not in data:
            return []

        rules = []
        for rule_data in data["rules"]:
            try:
                rule = DiagnosticRule(**rule_data)
                if rule.enabled:
                    rules.append(rule)
            except Exception:
                continue

        # 按优先级排序（高优先级在前）
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules

    def load_all_rules(self) -> list[DiagnosticRule]:
        """
        加载所有规则文件。

        Returns:
            规则列表
        """
        all_rules = []

        if not self.rules_path.exists():
            return all_rules

        for yaml_file in self.rules_path.glob("*.yaml"):
            rules = self.load_rules(yaml_file.name)
            all_rules.extend(rules)

        # 按优先级排序
        all_rules.sort(key=lambda r: r.priority, reverse=True)
        return all_rules