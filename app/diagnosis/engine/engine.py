"""规则引擎。"""

from datetime import datetime
from typing import Optional

from app.diagnosis.config import settings
from app.diagnosis.engine.loader import RuleLoader
from app.diagnosis.engine.rule import DiagnosticRule
from app.diagnosis.enums import ResultStatus, Stage
from app.diagnosis.schemas import DiagnosticResult, NormalizedEvent


class RuleEngine:
    """诊断规则引擎。"""

    def __init__(self, rules: Optional[list[DiagnosticRule]] = None):
        """
        初始化规则引擎。

        Args:
            rules: 规则列表，如果为None则从默认位置加载
        """
        if rules is None:
            loader = RuleLoader()
            self.rules = loader.load_all_rules()
        else:
            self.rules = rules

    def evaluate(
        self,
        run_id: str,
        events: list[NormalizedEvent],
    ) -> tuple[DiagnosticResult, list[DiagnosticRule]]:
        """
        对事件集执行规则匹配和诊断评估。

        Args:
            run_id: 任务ID
            events: 标准化事件列表

        Returns:
            (诊断结果, 匹配的规则列表)
        """
        # 提取事件代码集合
        event_codes = {event.normalized_code for event in events}

        # 确定最后阶段
        stage = self.determine_stage(events)

        # 查找所有匹配的规则
        matched_rules = []
        for rule in self.rules:
            # 阶段预筛选：对于有阶段限制的规则，快速检查是否有事件落在规则指定的阶段
            # 注意：这是预筛选逻辑，仅检查"是否存在相关阶段的事件"
            # 真正的阶段匹配逻辑在 rule.matches() 中完成，会同时考虑代码和阶段
            if rule.match_stage:
                rule_stages = {s.lower() for s in rule.match_stage}
                has_matching_stage = any(
                    e.stage.value.lower() in rule_stages for e in events
                )
                if not has_matching_stage:
                    continue

            # 检查事件代码匹配
            if rule.matches(event_codes, stage=None):  # stage检查已在上面完成
                matched_rules.append(rule)

        # 如果没有匹配规则，返回证据不足
        if not matched_rules:
            result = DiagnosticResult(
                run_id=run_id,
                stage=stage or Stage.PRECHECK,
                category="unknown",
                root_cause="insufficient_evidence",
                confidence=0.0,
                result_status=ResultStatus.INSUFFICIENT_EVIDENCE,
                key_evidence=[e.raw_line for e in events if e.raw_line][:5],
                next_action="collect more diagnostic evidence",
            )
            return result, []

        # 选择最佳规则（已按优先级排序）
        primary_rule = self._select_best_rule(matched_rules, events)

        # 确定结果阶段：优先使用规则指定的阶段，否则使用事件的最后阶段
        if primary_rule.match_stage:
            result_stage = Stage(primary_rule.match_stage[0])
        else:
            result_stage = stage or Stage.PRECHECK

        # 计算置信度
        confidence = self._calculate_confidence(primary_rule, events, matched_rules)

        # 提取关键证据
        key_evidence = self._extract_key_evidence(primary_rule, events)

        # 确定结果状态
        result_status = self._determine_result_status(primary_rule, events)

        result = DiagnosticResult(
            run_id=run_id,
            stage=result_stage,
            category=primary_rule.category,
            root_cause=primary_rule.root_cause or "unknown",
            confidence=confidence,
            result_status=result_status,
            key_evidence=key_evidence,
            next_action=primary_rule.next_action,
        )
        return result, matched_rules

    def determine_stage(self, events: list[NormalizedEvent]) -> Optional[Stage]:
        """
        确定诊断阶段（取最晚的阶段）。

        Args:
            events: 标准化事件列表

        Returns:
            最晚的阶段，如果没有事件则返回 PRECHECK
        """
        return self._determine_stage(events)

    def _determine_stage(self, events: list[NormalizedEvent]) -> Optional[Stage]:
        """确定诊断阶段（取最晚的阶段）。"""
        if not events:
            return Stage.PRECHECK

        stage_order = [
            Stage.PRECHECK,
            Stage.PACKAGE_PREPARE,
            Stage.APPLY_UPDATE,
            Stage.REBOOT_WAIT,
            Stage.POST_REBOOT,
            Stage.POST_VALIDATE,
        ]

        event_stages = {event.stage for event in events}
        for stage in reversed(stage_order):
            if stage in event_stages:
                return stage

        return Stage.PRECHECK

    def _select_best_rule(
        self,
        matched_rules: list[DiagnosticRule],
        events: list[NormalizedEvent],
    ) -> DiagnosticRule:
        """
        从匹配的规则中选择最佳规则。

        冲突消解策略：
        1. 优先级高的优先（priority 越大越优先）
        2. 晚阶段优先（后发生的阶段更可能是根本原因）
        3. 证据完整度优先（match_all 匹配比例越高越优先）
        """
        if len(matched_rules) == 1:
            return matched_rules[0]

        # 阶段顺序映射：数值越大表示阶段越靠后
        stage_order_map = {
            Stage.PRECHECK: 0,
            Stage.PACKAGE_PREPARE: 1,
            Stage.APPLY_UPDATE: 2,
            Stage.REBOOT_WAIT: 3,
            Stage.POST_REBOOT: 4,
            Stage.POST_VALIDATE: 5,
        }

        def evidence_completeness(rule: DiagnosticRule, events: list[NormalizedEvent]) -> float:
            """计算规则的证据完整度：match_all 匹配比例。"""
            if not rule.match_all:
                return 1.0  # 无 match_all 约束，视为完整匹配
            # 计算已匹配的唯一代码数量，避免同一代码多次出现导致完整度超过 1.0
            matched_codes = {e.normalized_code for e in events if e.normalized_code in rule.match_all}
            return len(matched_codes) / len(rule.match_all)

        def get_rule_stage_order(rule: DiagnosticRule) -> int:
            """获取规则的阶段顺序（取第一个定义的阶段）。"""
            if rule.match_stage:
                try:
                    stage_str = rule.match_stage[0].upper()
                    return stage_order_map.get(Stage(stage_str), 0)
                except ValueError:
                    return 0
            return 0

        # 按 priority 降序 -> stage_order 降序 -> evidence_completeness 降序 排序
        return sorted(
            matched_rules,
            key=lambda r: (
                -r.priority,  # 优先级高的优先
                -get_rule_stage_order(r),  # 后阶段优先
                -evidence_completeness(r, events),  # 证据完整度优先
            ),
        )[0]

    def _calculate_confidence(
        self,
        rule: DiagnosticRule,
        events: list[NormalizedEvent],
        matched_rules: list[DiagnosticRule],
    ) -> float:
        """
        计算诊断置信度。

        评分因素：
        1. 基础置信度（规则定义）
        2. 加分项：
           - 阶段连续性：事件跨越多个连续阶段
           - 多来源事件：来自不同日志源的事件
           - 关键证据数量充足
        3. 扣分项：
           - 多规则冲突
        """
        base = rule.base_confidence

        # 加分项1：阶段连续性（事件覆盖连续阶段）
        stage_order = [
            Stage.PRECHECK,
            Stage.PACKAGE_PREPARE,
            Stage.APPLY_UPDATE,
            Stage.REBOOT_WAIT,
            Stage.POST_REBOOT,
            Stage.POST_VALIDATE,
        ]
        event_stages = sorted(
            [event.stage for event in events],
            key=lambda s: stage_order.index(s) if s in stage_order else 0,
        )
        # 计算阶段跨度（连续阶段数）
        if event_stages:
            unique_stages = list(dict.fromkeys(event_stages))  # 保持顺序去重
            stage_span = len(unique_stages)
            if stage_span >= settings.confidence_stage_span_threshold:
                base = min(1.0, base + settings.confidence_stage_span_bonus)

        # 加分项2：多来源事件（来自不同日志源）
        event_sources = {event.source_type for event in events}
        if len(event_sources) >= settings.confidence_multi_source_threshold:
            base = min(1.0, base + settings.confidence_multi_source_bonus)

        # 加分项3：关键证据数量充足
        matched_events = [e for e in events if e.normalized_code in rule.match_all + rule.match_any]
        if len(matched_events) >= settings.confidence_evidence_count_threshold:
            base = min(1.0, base + settings.confidence_evidence_count_bonus)

        # 扣分项：多规则冲突（存在竞争规则）
        if len(matched_rules) > 1:
            base = max(0.0, base - settings.confidence_conflict_penalty * (len(matched_rules) - 1))

        return round(base, 2)

    def _extract_key_evidence(
        self,
        rule: DiagnosticRule,
        events: list[NormalizedEvent],
    ) -> list[str]:
        """提取关键证据。"""
        evidence = []

        # 收集匹配事件作为证据
        for code in rule.match_all + rule.match_any:
            for event in events:
                if event.normalized_code == code and event.raw_line:
                    evidence.append(event.raw_line)

        # 最多返回5条
        return evidence[:5]

    def _determine_result_status(
        self,
        rule: DiagnosticRule,
        events: list[NormalizedEvent],
    ) -> ResultStatus:
        """确定诊断结果状态。"""
        if rule.category == "success":
            return ResultStatus.PASSED

        if rule.category == "retryable_install_error":
            return ResultStatus.TRANSIENT_FAILURE

        return ResultStatus.FAILED