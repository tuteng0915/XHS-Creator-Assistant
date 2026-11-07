class ApplicationError(Exception):
    """Base class for errors that are safe to turn into API responses."""


class NotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class ValidationError(ApplicationError):
    pass


_TRANSPORT_REASONS = {
    "ConnectError": "无法连接模型服务",
    "ConnectTimeout": "连接模型服务超时",
    "ReadTimeout": "等待回复超时",
    "WriteTimeout": "发送请求超时",
    "PoolTimeout": "等待可用连接超时",
    "ReadError": "读取回复时连接中断",
    "WriteError": "发送请求时连接中断",
    "RemoteProtocolError": "模型服务中断了连接",
    "InvalidURL": "模型服务地址配置无效",
}


def transport_reason(kind: str) -> str:
    return _TRANSPORT_REASONS.get(kind, "网络请求失败")


class ModelTransportError(ValidationError):
    """No usable HTTP response arrived from the model service.

    Keeps the transport exception class name (``kind``) for records, never the
    endpoint URL or provider text. Subclasses ValidationError so existing API
    mapping and callers keep working.
    """

    def __init__(self, kind: str, *, provider: str = "") -> None:
        self.kind = kind
        self.provider = provider
        super().__init__(f"模型服务没有返回结果：{transport_reason(kind)}")

