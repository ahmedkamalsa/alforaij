#!/usr/bin/env python3
"""اختبار تلقائي لخادم MCP — يفتح الخادم عبر stdio ويتحقق من:

1. المصافحة: initialize يرد بإصدار البروتوكول واسم الملقم alforaij_mcp.
2. tools/list: 8 أدوات وكلها تحمل inputSchema.
3. tools/call: كل أداة تعمل (parse/search/rank/evaluate/compare/report/sources/opportunities).
4. أخطاء: طريقة مجهولة (-32601)، أداة مجهولة (-32602)، معامل ناقص (isError).
5. الإشعارات والـ ping تعمل بلا تعليق.

الاستخدام:  python mcp_server/smoke_test.py
الخروج: 0 عند النجاح، 1 عند أي فشل.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
EXPECTED_TOOLS = [
    "alforaij_parse_request",
    "alforaij_search_properties",
    "alforaij_rank_properties",
    "alforaij_evaluate_property",
    "alforaij_compare_properties",
    "alforaij_generate_report",
    "alforaij_list_sources",
    "alforaij_get_opportunities",
]


class McpClient:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(ROOT),
        )

    def call(self, message: dict) -> dict:
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def tool(self, name: str, arguments: dict) -> dict:
        response = self.call(
            {"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        assert "error" not in response, f"{name}: protocol error {response['error']}"
        result = response["result"]
        if result.get("isError"):
            return {"error": result["content"][0]["text"]}
        text = result["content"][0]["text"]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"markdown": text}

    def close(self) -> int:
        self.proc.stdin.close()
        return self.proc.wait(timeout=30)


def main() -> int:
    checks = 0
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
        if not condition:
            failures.append(label)

    client = McpClient()
    try:
        print("== المصافحة والبروتوكول ==")
        r = client.call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        result = r["result"]
        check("initialize returns serverInfo", result["serverInfo"]["name"] == "alforaij_mcp", str(result))
        check("initialize returns protocolVersion", str(result.get("protocolVersion", "")).startswith("2025-"), str(result))

        client.notify("notifications/initialized")

        r = client.call({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t["name"] for t in r["result"]["tools"]]
        check("tools/list has 8 tools", len(names) == 8, str(names))
        check("all expected tools present", all(name in names for name in EXPECTED_TOOLS), str(names))
        check("every tool has inputSchema", all("inputSchema" in t for t in r["result"]["tools"]))

        r = client.call({"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}})
        check("ping returns {}", r.get("result") == {}, str(r))

        r = client.call({"jsonrpc": "2.0", "id": 4, "method": "bogus/method", "params": {}})
        check("unknown method -> -32601", r.get("error", {}).get("code") == -32601, str(r))

        r = client.call({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
        check("unknown tool -> -32602", r.get("error", {}).get("code") == -32602, str(r))

        print("== الأدوات ==")

        r = client.tool("alforaij_parse_request", {"text": "مطلوب بيت في المطلاع مساحة 400"})
        req = r.get("request", {})
        check("parse_request extracts area المطلاع", req.get("areas") == ["المطلاع"], str(req))
        check("parse_request detects مطلوب للشراء", req.get("transaction") == "مطلوب للشراء", str(req))

        r = client.tool("alforaij_search_properties", {"transaction": "للبيع", "limit": 5, "format": "json"})
        check("search returns >0 results", r.get("total", 0) > 0, str(r.get("total")))
        items = r.get("items") or []
        check("search returns pagination fields", "hasMore" in r and "nextOffset" in r, str(sorted(r.keys())))
        codes = [i["code"] for i in items if i.get("code")]

        r = client.tool("alforaij_rank_properties", {"text": "مطلوب بيت في المطلاع مساحة 400", "limit": 3, "format": "json"})
        ranked = r.get("items") or []
        check("rank returns ranked results", len(ranked) > 0, str(r.get("error", "")))
        if ranked:
            check("rank includes recommendationScore", "recommendationScore" in ranked[0], str(sorted(ranked[0].keys())[:6]))

        if codes:
            r = client.tool("alforaij_evaluate_property", {"code": codes[0], "format": "json"})
            res = r.get("result") or {}
            check("evaluate returns valuation label", bool(res.get("valuationLabel")), str(r.get("error", "")))
            check("evaluate returns confidence", res.get("confidence") is not None, str(res.get("confidence")))

            r = client.tool("alforaij_compare_properties", {"codes": codes[:2], "format": "json"})
            check("compare returns entries", len(r.get("comparison") or []) == 2, str(r.get("error", "")))

        r = client.tool("alforaij_generate_report", {"text": "مطلوب بيت في المطلاع مساحة 400", "format": "json"})
        check("report includes summary", bool(r.get("summary")), str(r.get("error", "")))

        r = client.tool("alforaij_list_sources", {"format": "json"})
        check("sources lists records", r.get("totalRecords", 0) > 0, str(r.get("totalRecords")))

        r = client.tool("alforaij_get_opportunities", {"include_external": False, "limit_per_tier": 5, "format": "json"})
        check("opportunities returns tiers", bool((r.get("summary") or {}).get("tiers")), str(r.get("error", "")))

        print("== صيغ وأخطاء ==")
        r = client.tool("alforaij_search_properties", {"transaction": "للبيع", "limit": 2})
        check("markdown format works", "markdown" in r, str(r)[:80])

        r = client.tool("alforaij_rank_properties", {})
        check("missing param -> isError", "error" in r, str(r)[:80])

        r = client.tool("alforaij_evaluate_property", {"code": "XX-9999"})
        check("unknown code -> isError with guidance", "error" in r and "XX-9999" in r["error"], str(r)[:80])

        r = client.tool("alforaij_compare_properties", {"codes": ["XX-1"]})
        check("compare <2 codes -> isError", "error" in r, str(r)[:80])

        r = client.tool("alforaij_get_opportunities", {"limit_per_tier": 999})
        check("out-of-range param -> isError", "error" in r, str(r)[:80])
    finally:
        exit_code = client.close()
        print(f"\n== الخلاصة: {checks - len(failures)}/{checks} نجحت ==")
        if failures:
            print("فشلت:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
