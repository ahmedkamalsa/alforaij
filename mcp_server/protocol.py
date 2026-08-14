"""MCP stdio transport + JSON-RPC 2.0 — pure standard library.

نفذ بروتوكول Model Context Protocol للملقمات المحلية (stdio) بالطريقة الرسمية:
رسائل JSON-RPC 2.0 مفصولة بأسطر على stdin/stdout، مع معالجة:

- `initialize`        — المصافحة الأولية (إرجاع الإصدار والقدرات ومعلومات الملقم)
- `notifications/initialized` — إشعار بلا استجابة
- `tools/list`        — قائمة الأدوات بمخططاتها (JSON Schema)
- `tools/call`        — تنفيذ أداة وإرجاع محتوى نصي (isError عند الفشل)
- `ping`              — فحص الحيوية
- `shutdown` / `exit` — إنهاء الحلقة

أي طريقة أخرى تُرد بخطأ JSON-RPC -32601. كل الأسئلة تُميز بالـ `id`
والردود تحمل نفس المعرّف؛ الإشعارات (بلا id) لا تُجاب.

هذا الملف لا يعتمد على أي مكتبة خارجية — يلتزم بسياسة المشروع
«Python standard library only» الموثقة في requirements.txt.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

SERVER_NAME = "alforaij_mcp"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"

# أخطاء JSON-RPC القياسية (RFC 6749 قسم 5.1 + ملحق MCP)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """خطأ JSON-RPC يُرجع ككائن error في الاستجابة."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


def read_message(stream: Any = sys.stdin) -> dict[str, Any] | None:
    """قراءة رسالة JSON-RPC واحدة (سطر JSON) — ترجع None عند نهاية الإدخال."""
    line = stream.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return read_message(stream)
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {exc}") from exc
    if not isinstance(message, dict):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: message must be an object")
    return message


def write_message(message: dict[str, Any], stream: Any = sys.stdout) -> None:
    """كتابة رسالة JSON-RPC واحدة كسطر JSON مع flush فوري."""
    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    stream.flush()


def _response(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error_response(id_: Any, error: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": error}


class McpServer:
    """خادم MCP خفيف: يسجل الأدوات ويعالج الرسائل عبر حلقة stdio."""

    def __init__(self, tools: dict[str, dict[str, Any]]) -> None:
        self.tools = tools
        self._initialized = False

    # ── معالجة الأساليب ────────────────────────────────────────────────

    def handle_method(self, method: str, params: dict[str, Any] | None) -> Any:
        """تنفيذ طريقة وإرجاع نتيجتها — يرمي JsonRpcError عند الفشل."""
        params = params or {}
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [self._tool_info(tool) for tool in self.tools.values()]}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": []}
        if method == "completion/complete":
            raise JsonRpcError(INVALID_PARAMS, "No completions are registered on this server")
        raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        # نرد بنسخة نعرفها؛ ونعكس نسخة العميل إن كانت معروفة لتوافق أوسع مع العملاء.
        if isinstance(requested, str) and requested.startswith(("2024-", "2025-")):
            version = requested
        else:
            version = PROTOCOL_VERSION
        self._initialized = True
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _tool_info(self, tool: dict[str, Any]) -> dict[str, Any]:
        info: dict[str, Any] = {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
        }
        if "outputSchema" in tool:
            info["outputSchema"] = tool["outputSchema"]
        if "annotations" in tool:
            info["annotations"] = tool["annotations"]
        return info

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in self.tools:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"Unknown tool: {name!r}. Available: {', '.join(self.tools)}",
            )
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "arguments must be an object")
        handler: Callable[[dict[str, Any]], str] = self.tools[name]["handler"]
        try:
            text = handler(arguments)
        except JsonRpcError as exc:
            # أخطاء المدخلات/الاستخدام تُبلغ كأخطاء أدوات (وليس بروتوكول)
            return {
                "content": [{"type": "text", "text": exc.message}],
                "isError": True,
            }
        except Exception as exc:  # pragma: no cover — حماية أخيرة
            return {
                "content": [{"type": "text", "text": f"Error: {type(exc).__name__}: {exc}"}],
                "isError": True,
            }
        return {"content": [{"type": "text", "text": text}], "isError": False}

    # ── حلقة القراءة ───────────────────────────────────────────────────

    def serve_stdio(self, input_stream: Any = sys.stdin, output_stream: Any = sys.stdout) -> int:
        """تشغيل حلقة stdio حتى نهاية الإدخال — ترجع 0 عند الخروج النظيف."""
        while True:
            try:
                message = read_message(input_stream)
            except JsonRpcError as exc:
                write_message(_error_response(None, exc.to_dict()), output_stream)
                continue
            if message is None:
                return 0

            message_id = message.get("id")
            is_notification = "id" not in message
            method = message.get("method")
            params = message.get("params")

            if not isinstance(method, str):
                error = JsonRpcError(INVALID_REQUEST, "Invalid Request: missing 'method'")
                write_message(_error_response(message_id, error.to_dict()), output_stream)
                continue

            # الإشعارات المسموحة: لا استجابة
            if is_notification:
                if method in ("notifications/initialized", "notifications/cancelled"):
                    continue
                if method in ("shutdown", "exit"):
                    return 0
                # إشعار غير معروف يُتجاهل بصمت
                continue

            try:
                result = self.handle_method(method, params)
                write_message(_response(message_id, result), output_stream)
            except JsonRpcError as exc:
                write_message(_error_response(message_id, exc.to_dict()), output_stream)
            except Exception as exc:  # pragma: no cover
                error = JsonRpcError(INTERNAL_ERROR, f"Internal error: {type(exc).__name__}: {exc}")
                write_message(_error_response(message_id, error.to_dict()), output_stream)
        return 0
