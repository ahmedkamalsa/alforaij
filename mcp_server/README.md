# خادم MCP لمنصة الفريج

خادم [Model Context Protocol](https://modelcontextprotocol.io) رسمي عبر **stdio** —
بلا أي اعتماديات خارجية (Python standard library فقط، وفق سياسة المشروع).
يخدم نفس خط أنابيب المنصة: تفسير الطلبات، البحث، الترتيب حسب درجة التوصية،
التقييم بالمقارنات، المقارنة، التقرير الكامل، مصادر البيانات، وفرص المكسب.

## التشغيل

```powershell
cd D:\foraj_social\287\alforaij-research-assistant
python mcp_server\server.py
```

الخادم يقرأ رسائل JSON-RPC 2.0 من stdin ويكتبها على stdout (سطر لكل رسالة).
فحص سريع:

```powershell
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' | python mcp_server\server.py
```

الاختبار التلقائي الكامل (المصافحة + كل الأدوات + الأخطاء):

```powershell
python mcp_server\smoke_test.py
```

## الأدوات (8)

| الأداة | الوظيفة | المدخلات الرئيسية |
|---|---|---|
| `alforaij_parse_request` | تفسير طلب طبيعي إلى حقول منظمة | `text` |
| `alforaij_search_properties` | بحث بفلاتر منظمة مع ترقيم | `transaction`, `area`, `governorate`, `min_price`… |
| `alforaij_rank_properties` | ترتيب النتائج حسب درجة التوصية | `text`, `limit` |
| `alforaij_evaluate_property` | تقييم إعلان واحد (حكم سعر + مقارنات + ثقة) | `code`, `request_text?` |
| `alforaij_compare_properties` | مقارنة 2–10 إعلانات جنبًا إلى جنب | `codes[]` |
| `alforaij_generate_report` | تقرير البحث والتقييم الكامل | `text` |
| `alforaij_list_sources` | حالة المصادر وتوزيع البيانات | — |
| `alforaij_get_opportunities` | لقطة فرص المكسب الحالية | `include_external?` |

كل أداة تدعم `format: "markdown" | "json"` (markdown افتراضيًا، ما عدا
`evaluate_property` فالافتراضي json). كل الأدوات للقراءة فقط
(readOnlyHint) بلا أي تعديل على البيانات.

## الربط مع أي عميل MCP (Claude Desktop مثلًا)

أضف في إعدادات العميل خادمًا بمعرّف stdio:

```json
{
  "mcpServers": {
    "alforaij": {
      "command": "python",
      "args": ["D:\\foraj_social\\287\\alforaij-research-assistant\\mcp_server\\server.py"],
      "cwd": "D:\\foraj_social\\287\\alforaij-research-assistant"
    }
  }
}
```

> **ملاحظة Windows:** القناة مُهيأة لـ UTF-8 تلقائيًا (stdin/stdout/stderr) —
> بدونها تُفسد حروف العربية بترميز cp1252. لا حاجة لأي إعداد إضافي.

## أمثلة استدعاء

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"alforaij_rank_properties","arguments":{"text":"مطلوب بيت في المطلاع مساحة 400","limit":3}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"alforaij_evaluate_property","arguments":{"code":"AF-303"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"alforaij_get_opportunities","arguments":{"limit_per_tier":10}}}
```

## التصميم

- `protocol.py` — تنفيذ نقل stdio + JSON-RPC 2.0 (initialize, tools/list,
  tools/call, ping, notifications) مع أخطاء قياسية (-32700…-32603).
- `tools.py` — سجل الأدوات: مخططات JSON Schema + معالجات تستدعي خدمات
  backend الحقيقية (`parse_request` → `top_matches` → `enrich_rankings` →
  `build_report`) فيتطابق المخرج مع ما تعرضه المنصة تمامًا.
- `server.py` — نقطة الدخول وتهيئة UTF-8 للقناة.
- `smoke_test.py` — 25 فحصًا تلقائيًا عبر عملية فرعية حقيقية.

الأدوات بلا أي تأثير جانبي: لا كتابة، لا شبكة (ما عدا `get_opportunities`
عند `include_external: true` اختياريًا)، لا تتبع للطرف الثالث.
