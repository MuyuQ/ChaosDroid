"""TraceLens 统一异常处理模块。

定义 ServiceError 异常层次结构，用于服务层错误处理和 Web 层响应映射。
"""

from typing import Optional


class TraceLensError(Exception):
    """TraceLens 基础异常类。

    所有 TraceLens 业务异常都应继承此类。
    """

    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
    ):
        """初始化异常。

        Args:
            message: 错误消息
            details: 额外错误详情（可选）
        """
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        """转换为字典格式，用于 JSON 响应。"""
        result = {
            "error": self.__class__.__name__,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(TraceLensError):
    """输入验证错误。

    用于输入参数不合法的情况，如路径不存在、格式错误等。
    HTTP 状态码: 400 Bad Request
    """

    pass


class NotFoundError(TraceLensError):
    """资源不存在错误。

    用于请求的资源不存在的情况，如任务不存在、规则不存在等。
    HTTP 状态码: 404 Not Found
    """

    pass


class ParseError(TraceLensError):
    """解析失败错误。

    用于日志解析失败的情况，如文件格式错误、解析异常等。
    HTTP 状态码: 422 Unprocessable Entity
    """

    pass


class DiagnosisError(TraceLensError):
    """诊断失败错误。

    用于诊断执行失败的情况，如规则引擎异常、数据缺失等。
    HTTP 状态码: 500 Internal Server Error
    """

    pass


# HTTP 状态码映射
ERROR_STATUS_MAP = {
    ValidationError: 400,
    NotFoundError: 404,
    ParseError: 422,
    DiagnosisError: 500,
}


def get_status_code(error: TraceLensError) -> int:
    """根据异常类型获取对应的 HTTP 状态码。

    Args:
        error: TraceLens 异常实例

    Returns:
        HTTP 状态码
    """
    for error_type, status_code in ERROR_STATUS_MAP.items():
        if isinstance(error, error_type):
            return status_code
    # 默认返回 500
    return 500