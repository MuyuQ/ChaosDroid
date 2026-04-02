"""规则管理服务 - 异步版本。"""

from typing import Optional
import yaml
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.diagnosis.models import DiagnosticRuleDB
from app.diagnosis.engine.rule import DiagnosticRule
from app.diagnosis.config import settings
from app.diagnosis.enums import Category


class RuleService:
    """规则管理服务。"""

    def __init__(self, session: AsyncSession):
        """初始化服务。"""
        self.session = session

    async def list_rules(self, enabled_only: bool = False) -> list[DiagnosticRuleDB]:
        """
        获取规则列表。

        Args:
            enabled_only: 是否只返回启用的规则

        Returns:
            规则列表
        """
        stmt = select(DiagnosticRuleDB)
        if enabled_only:
            stmt = stmt.where(DiagnosticRuleDB.enabled == True)
        stmt = stmt.order_by(DiagnosticRuleDB.priority.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: str) -> Optional[DiagnosticRuleDB]:
        """
        获取单个规则。

        Args:
            rule_id: 规则 ID

        Returns:
            规则对象或 None
        """
        stmt = select(DiagnosticRuleDB).where(DiagnosticRuleDB.rule_id == rule_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_rule(self, data: dict) -> DiagnosticRuleDB:
        """
        创建新规则。

        Args:
            data: 规则数据

        Returns:
            创建的规则对象
        """
        # 将字符串 category 转换为 Category 枚举
        category_value = data.get("category")
        if isinstance(category_value, str):
            category_enum = Category(category_value)
        else:
            category_enum = category_value

        rule = DiagnosticRuleDB(
            rule_id=data["rule_id"],
            name=data["name"],
            priority=data.get("priority", 50),
            enabled=data.get("enabled", True),
            match_all=data.get("match_all", []),
            match_any=data.get("match_any", []),
            exclude_any=data.get("exclude_any", []),
            match_stage=data.get("match_stage", []),
            category=category_enum,
            root_cause=data.get("root_cause"),
            base_confidence=data.get("base_confidence", 0.9),
            next_action=data.get("next_action"),
        )
        self.session.add(rule)
        await self.session.commit()
        return rule

    async def update_rule(self, rule_id: str, data: dict) -> Optional[DiagnosticRuleDB]:
        """
        更新规则。

        Args:
            rule_id: 规则 ID
            data: 更新数据

        Returns:
            更新后的规则对象或 None
        """
        rule = await self.get_rule(rule_id)
        if not rule:
            return None

        for key, value in data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        await self.session.commit()
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """
        删除规则。

        Args:
            rule_id: 规则 ID

        Returns:
            是否删除成功
        """
        rule = await self.get_rule(rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        await self.session.commit()
        return True

    async def export_to_yaml(self, file_path: Optional[Path] = None) -> dict:
        """
        导出规则到 YAML 文件。

        Args:
            file_path: 导出文件路径，默认为 core_rules.yaml

        Returns:
            导出的规则数据
        """
        rules = await self.list_rules()
        rules_data = {
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "priority": r.priority,
                    "enabled": r.enabled,
                    "match_all": r.match_all,
                    "match_any": r.match_any,
                    "exclude_any": r.exclude_any,
                    "match_stage": r.match_stage,
                    "category": r.category,
                    "root_cause": r.root_cause,
                    "base_confidence": r.base_confidence,
                    "next_action": r.next_action,
                }
                for r in rules
            ]
        }

        if file_path is None:
            file_path = settings.rules_path / "core_rules.yaml"

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(rules_data, f, allow_unicode=True, default_flow_style=False)

        return rules_data

    async def import_from_yaml(self, file_path: Optional[Path] = None) -> int:
        """
        从 YAML 文件导入规则。

        Args:
            file_path: 导入文件路径，默认为 core_rules.yaml

        Returns:
            导入的规则数量
        """
        if file_path is None:
            file_path = settings.rules_path / "core_rules.yaml"

        if not file_path.exists():
            return 0

        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "rules" not in data:
            return 0

        count = 0
        for rule_data in data["rules"]:
            # 检查是否已存在
            existing = await self.get_rule(rule_data["rule_id"])
            if existing:
                # 更新现有规则
                await self.update_rule(rule_data["rule_id"], rule_data)
            else:
                # 创建新规则
                await self.create_rule(rule_data)
            count += 1

        return count

    async def load_rules_for_engine(self) -> list[DiagnosticRule]:
        """
        加载规则供规则引擎使用。

        如果数据库中没有规则，会自动从 YAML 文件导入。

        Returns:
            DiagnosticRule 列表
        """
        rules_db = await self.list_rules(enabled_only=True)

        # 如果数据库中没有规则，从 YAML 文件导入
        if not rules_db:
            await self.import_from_yaml()
            rules_db = await self.list_rules(enabled_only=True)

        rules = []
        for r in rules_db:
            # 将 Category 枚举转换为字符串
            category_str = r.category.value if hasattr(r.category, 'value') else r.category

            rule = DiagnosticRule(
                rule_id=r.rule_id,
                name=r.name,
                priority=r.priority,
                enabled=r.enabled,
                match_all=r.match_all,
                match_any=r.match_any,
                exclude_any=r.exclude_any,
                match_stage=r.match_stage,
                category=category_str,
                root_cause=r.root_cause,
                base_confidence=r.base_confidence,
                next_action=r.next_action,
            )
            rules.append(rule)
        return rules
