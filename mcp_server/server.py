#!/usr/bin/env python3
"""خادم MCP لمنصة الفريج — بروتوكول MCP رسمي عبر stdio.

يخدم 8 أدوات مبنية على خدمات backend الفعلية (نفس خط أنابيب المنصة):
تفسير الطلبات، البحث، الترتيب حسب درجة التوصية، التقييم، المقارنة،
توليد التقرير، مصادر البيانات، وفرص المكسب.

الاستخدام:
  - كخادم MCP لأي عميل (Claude Desktop، محررات، وكلاء):
        mcp_server/server.py
  - فحص سريع عبر الأنبوب:
        echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python mcp_server/server.py

بلا أي اعتماديات خارجية — Python standard library فقط (سياسة المشروع).
"""

from __future__ import annotations

import sys

from protocol import McpServer, SERVER_NAME, SERVER_VERSION
from tools import TOOLS


def main() -> int:
    # قناة MCP يجب أن تكون UTF-8 دائمًا (خصوصًا على Windows حيث الافتراضي cp1252)
    # — stdin أيضًا: بدونها تُفكَّك حروف العربية بترميز cp1252+surrogateescape فتُفسد المدخلات.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    server = McpServer(TOOLS)
    return server.serve_stdio()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
