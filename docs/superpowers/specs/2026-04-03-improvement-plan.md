# ChaosDroid 项目改进方案

**创建日期**: 2026-04-03  
**实施优先级**: 高优先级问题优先

---

## 执行摘要

本改进方案基于项目审查报告，针对 ChaosDroid 项目整合后发现的问题进行系统性修复。

**项目当前整合状态**：
- **原始 ChaosDroid 核心** (约 60%) - 故障注入器、执行编排、调度层
- **TraceLens 完整集成** (约 25%) - 日志分析诊断引擎  
- **AegisOTA 参考** (约 15%) - 中间件、项目组织、模板样式

---

## 问题清单与解决方案

### 高优先级问题（P0 - 需要立即解决）

#### P0-1: 诊断模块使用同步 SQLAlchemy

**问题描述**：
诊断模块 (`app/diagnosis/models/db.py`) 使用同步 SQLAlchemy (`sqlite://`)，而主应用 (`app/models/database.py`) 使用异步 SQLAlchemy (`sqlite+aiosqlite://`)，导致架构不兼容。

**解决方案**：

1. **修改 `app/diagnosis/models/db.py`** - 迁移到异步 SQLAlchemy：
   - 从 `sqlalchemy` 改为 `sqlalchemy.ext.asyncio`
   - 使用 `create_async_engine` 和 `async_sessionmaker`
   - 将 `get_session()` 改为异步生成器

2. **更新所有诊断服务** - 使用异步会话（5 个文件）

3. **更新诊断 API 路由** - 使用异步依赖注入

**需要修改的文件**：
- `app/diagnosis/models/db.py` - 核心修改
- `app/diagnosis/services/*.py` - 5 个服务文件
- `app/api/routes/diagnosis.py` - API 路由
- `app/diagnosis/web/app.py` - Web 页面路由

**预计工作量**: 1-2 天

---

#### P0-2: 规则引擎未与主数据库集成

**问题描述**：
诊断规则目前从 YAML 文件加载 (`app/diagnosis/engine/loader.py`)，而非使用数据库存储。

**解决方案**：

1. **在 `app/diagnosis/engine/loader.py` 添加 `DatabaseRuleLoader` 类**：
   ```python
   class DatabaseRuleLoader:
       def __init__(self, session: AsyncSession):
           self.session = session
       
       async def load_all_rules(self) -> list[DiagnosticRule]:
           # 从数据库查询 DiagnosticRuleDB 并转换为 DiagnosticRule
   ```

2. **修改 `app/diagnosis/services/diagnose.py`** - 使用异步数据库加载规则

3. **启动时规则迁移** - 检查数据库是否有规则，若无则从 YAML 导入

**需要修改的文件**：
- `app/diagnosis/engine/loader.py` - 添加 DatabaseRuleLoader
- `app/diagnosis/services/diagnose.py` - 使用异步规则加载

**依赖关系**：依赖 P0-1（需要先完成异步迁移）

**预计工作量**: 0.5-1 天

---

#### P0-3: CSRF 中间件逻辑重复

**问题描述**：
存在两套 CSRF 实现：
1. `app/api/main.py` - `CSRFMiddleware` 类（自定义实现）
2. `app/diagnosis/web/csrf.py` - `fastapi_csrf_protect` 库实现

**解决方案**：

1. **删除 `app/diagnosis/web/csrf.py`** - 移除重复实现

2. **增强 `app/api/main.py` 的 CSRF 中间件** - 添加密钥配置和统一验证逻辑

3. **在 `app/config/settings.py` 添加 CSRF 配置**：
   ```python
   csrf_secret: str = Field(
       default="change-me-in-production",
       description="CSRF 密钥，生产环境必须修改"
   )
   ```

4. **更新 `app/diagnosis/web/app.py`** - 移除对 csrf.py 的依赖

**需要修改的文件**：
- `app/api/main.py` - 增强 CSRF 中间件
- `app/diagnosis/web/csrf.py` - 删除文件
- `app/diagnosis/web/app.py` - 移除依赖
- `app/config/settings.py` - 添加 CSRF 配置

**预计工作量**: 0.5 天

---

#### P0-4: 诊断 API 未完全集成服务层

**问题描述**：
诊断 API 直接创建服务实例，缺少统一的异常处理和会话管理。

**解决方案**：

1. **使用依赖注入管理会话**：
   ```python
   @router.post("/run", response_model=DiagnoseResponse)
   async def run_diagnose(
       request: DiagnoseRequest,
       session: AsyncSession = Depends(get_session)
   ):
   ```

2. **在 `app/api/main.py` 添加全局异常处理器**：
   ```python
   @app.exception_handler(DiagnosisError)
   async def diagnosis_error_handler(request: Request, exc: DiagnosisError):
       return JSONResponse(status_code=500, content={"detail": str(exc.message)})
   ```

**需要修改的文件**：
- `app/api/routes/diagnosis.py` - 使用依赖注入
- `app/api/main.py` - 添加异常处理器

**依赖关系**：依赖 P0-1（异步迁移）

**预计工作量**: 0.5 天

---

### 中优先级问题（P1 - 重要但可延后）

#### P1-1: 模板文件重复

**问题描述**：
以下模板文件在两个目录中完全重复：
- `base.html`
- `dashboard.html`
- `dashboard_task_list.html`
- `import.html`
- `api_docs.html`

**解决方案**：

1. **统一模板目录到 `app/templates/`**

2. **删除重复文件**：
   - 删除 `app/api/templates/diagnosis/` 目录
   - 保留 `app/diagnosis/web/templates/` 中的特有模板（rules/, cases/, runs/）

3. **更新模板加载路径**

**需要修改的文件**：
- `app/api/main.py` - 更新模板目录
- `app/diagnosis/web/app.py` - 更新模板目录

**预计工作量**: 0.5 天

---

#### P1-2: 日志配置不统一

**问题描述**：
存在两套日志配置（`app/config/logging.py` 和 `app/diagnosis/config.py`）

**解决方案**：
- 统一日志配置到 `app/config/logging.py`
- 从 `app/diagnosis/config.py` 移除日志相关代码

**预计工作量**: 0.5 天

---

#### P1-3: 相似案例功能未启用

**问题描述**：
`SimilarCaseService` 已实现但未集成到主应用诊断流程中。

**解决方案**：
在诊断流程中调用相似案例检索：
```python
# app/diagnosis/services/diagnose.py
async def diagnose(self, run_id: str) -> DiagnosticResult:
    result = await self._run_diagnosis(run_id)
    # 检索相似历史案例
    similar_cases = await self.similar_service.search(result, limit=3)
    result.similar_cases = similar_cases
    return result
```

**需要修改的文件**：
- `app/diagnosis/services/diagnose.py` - 集成相似案例
- `app/diagnosis/schemas.py` - 添加 similar_cases 字段
- `app/api/routes/diagnosis.py` - API 响应包含相似案例

**预计工作量**: 0.5-1 天

---

## 实施优先级和依赖关系

### 阶段一：架构统一 (P0 问题) - 3-4 天

```
┌─────────────────────────────────────────────────────────┐
│  任务 1: CSRF 中间件整合     │  无依赖    │  第 1 天    │
├─────────────────────────────────────────────────────────┤
│  任务 2: 异步数据库迁移      │  无依赖    │  第 1-2 天  │
├─────────────────────────────────────────────────────────┤
│  任务 3: 服务层异步改造      │  依赖任务 2 │  第 2-3 天  │
├─────────────────────────────────────────────────────────┤
│  任务 4: API 路由依赖注入    │  依赖任务 3 │  第 3 天    │
├─────────────────────────────────────────────────────────┤
│  任务 5: 规则引擎数据库集成  │  依赖任务 3 │  第 3-4 天  │
└─────────────────────────────────────────────────────────┘
```

### 阶段二：功能整合 (P1 问题) - 2-3 天

```
┌─────────────────────────────────────────────────────────┐
│  任务 1: 模板文件整合       │  无依赖    │  第 1 天    │
├─────────────────────────────────────────────────────────┤
│  任务 2: 日志配置统一       │  无依赖    │  第 1 天    │
├─────────────────────────────────────────────────────────┤
│  任务 3: 相似案例集成       │  依赖阶段一 │  第 2 天    │
├─────────────────────────────────────────────────────────┤
│  任务 4: 规则管理 UI        │  依赖阶段一 │  第 2-3 天  │
└─────────────────────────────────────────────────────────┘
```

---

## 验证方案

### CSRF 中间件验证
```bash
# 测试无 CSRF token 的请求应返回 403
curl -X POST http://localhost:8000/api/diagnosis/run \
  -H "Content-Type: application/json" \
  -d '{"run_id": "test"}'

# 测试有效 CSRF token 应成功
curl -X POST http://localhost:8000/api/diagnosis/run \
  -H "X-CSRF-Token: <token>" \
  -H "Cookie: csrf_token=<token>" \
  -d '{"run_id": "test"}'
```

### 异步数据库验证
```bash
# 并发测试确认无死锁
ab -n 100 -c 10 http://localhost:8000/api/diagnosis/run
```

### 规则数据库集成验证
```python
from app.diagnosis.services import RuleService
service = RuleService()
rules = service.list_rules()
assert len(rules) > 0, "规则应从数据库加载"
```

---

## 关键文件清单

### 核心修改文件（10 个）
1. `app/diagnosis/models/db.py`
2. `app/diagnosis/services/diagnose.py`
3. `app/diagnosis/services/rule.py`
4. `app/diagnosis/services/similar.py`
5. `app/diagnosis/services/ingest.py`
6. `app/diagnosis/services/report.py`
7. `app/api/routes/diagnosis.py`
8. `app/api/main.py`
9. `app/diagnosis/engine/loader.py`
10. `app/config/settings.py`

### 删除文件
- `app/diagnosis/web/csrf.py`

---

## 总结

本方案遵循**代码改动最小化**原则，优先解决高优先级的架构问题。实施完成后，ChaosDroid 项目将拥有：
- 统一的异步数据库架构
- 单一的 CSRF 保护实现
- 数据库驱动的规则管理
- 整合的模板系统
- 完整的相似案例功能
