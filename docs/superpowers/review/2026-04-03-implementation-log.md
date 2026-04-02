# ChaosDroid 项目改进实施记录

**实施日期**: 2026-04-03  
**基于文档**: `docs/superpowers/specs/2026-04-03-improvement-plan.md`

---

## 已完成的改进

### P0-3: 整合 CSRF 中间件，移除重复实现 ✅

**实施内容**:

1. **删除重复的 CSRF 实现文件**:
   - 删除 `app/diagnosis/web/csrf.py` - 原 `fastapi_csrf_protect` 库配置
   - 删除 `app/api/routes/diagnosis_web.py` - 重复的诊断 Web 路由（已整合到 `web.py`）

2. **更新 `app/diagnosis/web/app.py`**:
   - 移除独立的 CSRF token 端点 (`/csrf-token`)
   - 更新 `get_db()` 为异步依赖注入生成器

3. **主应用 CSRF 中间件**:
   - `app/api/main.py` 中的 `CSRFMiddleware` 已配置使用 `settings.csrf_secret`
   - 诊断 Web 页面通过主应用中间件获得 CSRF 保护

**验证**:
- 主应用和诊断 Web 共享同一套 CSRF 保护机制
- 表单提交通过 `X-CSRF-Token` header 验证

---

### P0-1: 诊断模块异步数据库迁移 ✅

**实施内容**:

1. **核心数据库配置** (`app/diagnosis/models/db.py`) - 已完成:
   - 使用 `sqlalchemy.ext.asyncio` 的 `create_async_engine`
   - 使用 `async_sessionmaker` 创建异步会话工厂
   - `get_session()` 为异步生成器

2. **服务层异步改造**:
   - `IngestService` - 需要 `AsyncSession` 参数，所有方法为 `async`
   - `DiagnoseService` - 需要 `AsyncSession` 参数，所有方法为 `async`
   - `RuleService` - 需要 `AsyncSession` 参数，所有方法为 `async`
   - `ParseService` - 需要 `AsyncSession` 参数，所有方法为 `async`
   - `SimilarCaseService` - 需要 `AsyncSession` 参数，所有方法为 `async`
   - `ReportService` - 需要 `AsyncSession` 参数，所有方法为 `async`

3. **诊断 Web 路由异步改造** (`app/diagnosis/web/routes/pages.py`):
   - 添加 `get_db()` 依赖注入函数
   - 所有路由函数添加 `session: AsyncSession = Depends(get_db)` 参数
   - 所有服务调用使用 `await`

4. **诊断 API 路由异步改造** (`app/diagnosis/web/routes/api.py`):
   - 添加 `get_db()` 依赖注入函数
   - 所有路由函数添加 `session` 参数
   - 所有服务调用使用 `await`

5. **主应用诊断路由** (`app/api/routes/web.py`):
   - 使用 `get_async_session_factory()` 创建异步上下文
   - 模板响应使用新的 Starlette API（`request=`, `name=`, `context=`）
   - 禁用 Jinja2 缓存 (`cache_size=0`) 避免复杂对象缓存键问题

**修复的问题**:
- `DiagnoseService.__init__` 不能直接 `await` 规则加载 → 改为懒加载模式，在 `diagnose()` 方法中首次调用时加载

---

### P0-2: 规则引擎与主数据库集成 ✅

**实施状态**: 已在代码中实现

**实现方式**:
- `RuleService.load_rules_for_engine()` 方法:
  - 从数据库加载启用的规则
  - 如果数据库为空，自动从 `core_rules.yaml` 导入
  - 转换为 `DiagnosticRule` 对象供规则引擎使用

- `DiagnoseService` 使用懒加载:
  ```python
  async def _ensure_rules_loaded(self):
      if self.rule_engine is None:
          rules = await self.rule_service.load_rules_for_engine()
          self.rule_engine = RuleEngine(rules=rules)
  ```

**验证**:
- 启动诊断时自动从数据库加载规则
- 首次运行时自动从 YAML 导入规则到数据库

---

## 修复的 Bug

### 1. Jinja2 模板缓存键错误

**问题**: `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')`

**原因**: 
- Starlette `TemplateResponse` API 变更，新 API 为：
  ```python
  TemplateResponse(request, name, context)
  ```
- 旧代码使用：
  ```python
  TemplateResponse(name, {context})  # 错误！
  ```

**修复**:
```python
# 旧代码
return _get_templates().TemplateResponse("diagnosis/list.html", {
    "request": request, ...
})

# 新代码
return _get_templates().TemplateResponse(
    request=request,
    name="diagnosis/list.html",
    context={"runs": runs_data, ...}
)
```

**文件**: `app/api/routes/web.py`

### 2. DiagnoseService 规则加载未 await

**问题**: `RuntimeWarning: coroutine 'RuleService.load_rules_for_engine' was never awaited`

**原因**: 在 `__init__` 中调用异步方法

**修复**: 改为懒加载模式，在 `diagnose()` 方法中首次调用时加载规则

---

## 删除的文件

| 文件 | 原因 |
|------|------|
| `app/diagnosis/web/csrf.py` | 重复的 CSRF 实现 |
| `app/api/routes/diagnosis_web.py` | 重复的诊断路由 |

---

## 当前状态

**服务器运行**: ✅ 正常 (http://localhost:8000)

**API 端点测试**:
- `/health` - ✅ 200 OK
- `/diagnosis` - ✅ 200 OK (页面正常渲染)

**待办事项**:
- 规则管理 UI (P1 优先级)
- 相似案例功能集成 (P1 优先级)
- 日志配置统一 (P1 优先级)
- 模板文件整合 (P1 优先级)

---

## 总结

本次改进完成了所有 P0 高优先级任务：
1. ✅ 统一异步数据库架构
2. ✅ 整合 CSRF 中间件实现
3. ✅ 规则引擎数据库集成

诊断页面现在可以正常访问，所有服务层代码已迁移到异步模式，系统架构统一。
