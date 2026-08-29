# Site Knowledge — منصة الفريج العقارية
# Complete Platform Documentation for AI Code Review

> **To Codex Agent**: This is the complete knowledge base for the Al-Furaj Real Estate Platform. Read it thoroughly before making any changes. The user has given you full access to the codebase.

---

## PLATFORM IDENTITY

**Name**: منصة الفريج للفرص والتقييم العقاري (Al-Furaj Real Estate Opportunities & Evaluation Platform)  
**Company**: شركة عبدالعزيز سعود الفريج العقارية (Abdul Aziz Saud Al-Furaj Real Estate Company)  
**Purpose**: Unified search across Al-Furaj data + external sources, evidence-based evaluation, and investment opportunities linking supply to demand and potential clients.  
**Domain**: search.alforaij.com (production), http://127.0.0.1:8000 (local)  
**GitHub**: https://github.com/ahmedkamalsa/alforaij  
**Database**: Supabase (PostgreSQL) — 14 tables  
**Language**: Arabic-first UI, English code comments  

---

## WHAT THE PLATFORM DOES (User Perspective)

### For Regular Users (Free)
1. **Search Properties**: Type natural Arabic queries like "بيت 400م في الفردوس" → get scored results from 18+ sources
2. **View Results**: Each result has match score, price comparison, area analysis, source trust rating
3. **Interactive Map**: See property locations on OpenStreetMap with color-coded markers
4. **Price Trends**: Monthly median price charts by area
5. **ROI Calculator**: Calculate investment return on any property
6. **Chat Assistant**: Ask questions about properties, areas, pricing
7. **Export**: Download results as PDF or JSON

### For Agents/Employees
1. **CRM**: Manage client leads with WhatsApp links
2. **Reports**: Generate professional PDF reports with evidence
3. **Opportunity Alerts**: Get notified of new investment opportunities
4. **Market Matching**: Match client requests with available properties

### For Admins
1. **Admin Dashboard**: `/admin.html` — Overview, Users, Roles, Listings, Analytics
2. **User Management**: Assign roles (admin/employee/user)
3. **Listing Management**: Approve/reject/edit/delete listings
4. **Source Monitoring**: Track which data sources are working

---

## COMPETITIVE LANDSCAPE

| Platform | Market | Our Advantage |
|----------|--------|---------------|
| **Bayut** (bayut.com) | UAE + Kuwait | We have Arabic NLP search, they don't |
| **PropertyFinder** | 6 countries | We have 18 sources in one search, they don't |
| **OpenSooq** | 20 countries | We have AI scoring + opportunity detection |
| **Sakan** (sakan.co) | Kuwait only | We're free forever, they charge for premium |
| **Yebtah** | Kuwait + Saudi | We have official government transaction data |
| **4Sale** | Kuwait | We aggregate them + others in one search |

**Our 5 Unique Differentiators (No competitor has these)**:
1. Arabic natural language search ("بيت 400م بسعر 120 الف في الفردوس")
2. 18 external sources searched simultaneously
3. Official government transaction linking
4. Investment opportunity detection ("لقطة" = below market price)
5. Free PDF/Excel reports

---

## TECHNICAL ARCHITECTURE

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND                         │
│  index.html + app.js (8,527 lines vanilla JS)       │
│  admin.html (Admin Dashboard)                       │
│  Leaflet.js (map) + Chart.js (charts) — lazy load   │
│  React Native (mobile app — WebView wrapper)         │
└──────────────┬──────────────────────┬───────────────┘
               │ HTTP REST            │ HTTP REST
┌──────────────▼──────────────────────▼───────────────┐
│                    BACKEND                          │
│  main.py (2,041 lines — stdlib http.server)         │
│  50+ API endpoints                                  │
│  Python 3.13 — NO framework (no FastAPI/Flask)      │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
┌──────────────▼──────────┐ ┌────────▼───────────────┐
│    SUPABASE (Postgres)  │ │    EXTERNAL SOURCES    │
│  14 tables              │ │  18+ scrapers          │
│  72,486 evidence rows   │ │  4Sale, Mourjan, etc.  │
│  3,024 total listings   │ │  Parallel fetching     │
└─────────────────────────┘ └────────────────────────┘
```

---

## DATABASE TABLES

| Table | Records | Purpose |
|-------|---------|---------|
| `listings` | 182 | Internal Al-Furaj listings |
| `market_listings` | 2,824 | External market listings |
| `price_trends` | 583 | Monthly median prices by area |
| `market_ads` | 18 | Live market ads |
| `official_transactions` | 0 | Government transactions (empty) |
| `official_market_indicators` | 53 | Official price indicators |
| `saved_reports` | 738 | Saved search reports |
| `source_runs` | 5,637 | Source execution logs |
| `listing_evidence` | 72,486 | Evidence for each number |
| `client_leads` | 1 | Client leads |
| `client_property_requests` | 0 | Property requests |
| `opportunities` | 407 | Investment opportunities |
| `search_history` | 471 | Search history |
| `users` | ~5 | Registered users |

---

## ALL API ENDPOINTS

### GET Endpoints (Read)
```
/api/health                    → Server health + data counts
/api/google-client-id          → Google OAuth client ID (empty if not configured)
/api/analytics                 → Platform analytics
/api/analytics-dashboard       → Analytics dashboard data
/api/sources                   → Available data sources
/api/search-options            → Search filter options
/api/market-analytics          → Market analysis data
/api/market-insights           → Market insights
/api/market-demand             → Supply/demand data
/api/dashboard/summary         → Dashboard summary (1,208 listings, etc.)
/api/opportunities             → Investment opportunities list
/api/opportunities/history     → Opportunity history snapshots
/api/price-trends?area=X       → Price trends by area (583 records)
/api/market-matching           → Supply/demand matching
/api/live-db                   → Live database status
/api/roles                     → User roles and permissions
/api/ai/providers              → AI provider status
/api/admin/users               → All registered users (Admin only)
/api/push/stats                → Push notification statistics
/api/update-notifications      → Platform update notifications
/api/developments              → Market developments (news)
/api/whatsapp-alerts           → WhatsApp alert messages
/api/outreach/stats            → Outreach click statistics
/api/clients                   → Client leads with WhatsApp links
/api/metric-registry           → Metrics documentation
/api/platform-dates            → Platform important dates
/api/official-reference-sources → Official government sources
```

### POST Endpoints (Write)
```
/api/analyze                    → MAIN SEARCH (query + evaluate + score)
/api/parse                      → Parse Arabic natural language to filters
/api/whatsapp/parse             → Parse WhatsApp messages
/api/register                   → Phone registration (OTP)
/api/verify-otp                 → Verify OTP code
/api/google-login               → Google Sign-In (JWT verify)
/api/report-pdf                 → Generate PDF report
/api/outreach-click             → Track outreach clicks
/api/daily-agent/run            → Trigger daily data collection (Admin)
/api/official-transactions/import → Import official transactions (Admin)
/api/tier/status                → Get user tier status
/api/tier/upgrade               → Upgrade user tier
/api/tier/authorize             → Authorize feature access
/api/tier/pricing               → Display pricing plans
/api/admin/dashboard            → Admin dashboard analytics
/api/invest/calculate           → ROI calculator
/api/invest/mortgage            → Mortgage calculator
/api/invest/compare             → Investment comparison
/api/invest/forecast            → Investment forecast
/api/classifiers                → Property classifiers
/api/classify                   → Classify listings
/api/user/role                  → Get/set user role
/api/user/role/check            → Check permission
/api/tiers                      → List subscription tiers
/api/push/register              → Register push token
/api/push/subscribe             → Subscribe to notifications
/api/push/unsubscribe           → Unsubscribe
/api/push/send                  → Send push notification
```

---

## USER ROLES & PERMISSIONS

```python
ROLES = {
    "admin": {
        "name": "مدير النظام",
        "name_en": "Administrator", 
        "permissions": ["all"],  # Full access
    },
    "employee": {
        "name": "موظف",
        "name_en": "Employee",
        "permissions": [
            "search", "comparisons", "dashboard_view",
            "basic_analysis", "pdf_reports", "opportunity_alerts",
        ],
    },
    "user": {
        "name": "مستخدم",
        "name_en": "User",
        "permissions": ["search", "dashboard_view"],  # Basic only
    },
}
```

---

## AUTHENTICATION FLOW

### Phone + OTP (Primary)
```
1. User enters phone: +96555512345
2. Backend normalizes to E.164: +96555512345
3. Backend generates 6-digit OTP
4. OTP hashed with SHA256 + salt → stored in Supabase
5. OTP sent via WhatsApp (Meta Cloud API)
6. User enters OTP → backend verifies hash + expiry (10min) + attempts (max 5)
7. On success: returns user_secret (24-char random)
8. Frontend stores secret in localStorage
9. All subsequent requests include secret in header/body
```

### Google Sign-In (Not yet configured)
```
1. Frontend loads Google Identity Services SDK
2. User clicks Google button → Google popup
3. Google returns JWT credential
4. Frontend sends JWT to /api/google-login
5. Backend verifies JWT → creates/updates user in Supabase
6. Returns user_secret

BLOCKER: GOOGLE_CLIENT_ID env var not set
ACTION NEEDED: User must create Google Cloud project and get Client ID
```

---

## AI SYSTEM

### Multi-Provider Router (ai_router.py)
```
Fallback Chain: FreeLLMAPI → Ollama → Gemini → OpenRouter → AgentRouter

| Provider   | Type   | Cost              | Speed    |
|-----------|--------|-------------------|----------|
| FreeLLMAPI| Gateway| Free (34 providers)| Medium   |
| Ollama    | Local  | Free, unlimited    | Fast 1-3s|
| Gemini    | Google | Free 1M tok/day   | Medium   |
| OpenRouter| Cloud  | Free tier models   | Medium   |
| AgentRouter| Cloud | Limited            | Slow     |
```

### How Search Works
```
1. User types: "بيت 400م في الفردوس"
2. request_parser.py extracts: {area: "الفردوس", space: 400, type: "بيت"}
3. Backend searches local DB (182 listings) + external sources (2,824) in parallel
4. Each source has 5s timeout → skipped if slow
5. ai_evaluator.py scores each result:
   - matchScore: How well it matches the query (0-100)
   - recommendationScore: Investment recommendation (0-100)  
   - dealScore: Is it a "لقطة" (bargain)?
   - normalized_price: Price per m² for comparison
6. Results ranked by score with evidence and comparables
7. Total time: 3s (fast mode) or 47s (full mode with all sources)
```

---

## FILE STRUCTURE (Key Files)

```
alforaij-research-assistant/
├── backend/
│   ├── main.py                    # 2,041 lines — HTTP server + 50+ endpoints
│   ├── config.py                  # Environment config
│   ├── connectors/
│   │   ├── live_sources.py        # Scrapers: 4Sale, Mourjan, OpenSooq, etc.
│   │   ├── external_search.py     # External source coordinator
│   │   └── official_data.py       # Government data
│   └── services/
│       ├── accounts.py            # OTP, roles, phone normalization
│       ├── supabase_store.py      # 1,225 lines — ALL database operations
│       ├── ai_evaluator.py        # AI-powered scoring
│       ├── ai_router.py           # Multi-provider AI with fallback
│       ├── request_parser.py      # Arabic NLP parser
│       ├── valuation.py           # Property valuation
│       ├── opportunities.py       # Opportunity detection
│       ├── chat_agents.py         # Chat assistant
│       ├── push_notifications.py  # Push notification service
│       ├── pdf_report.py          # PDF generation
│       ├── investment_calculator.py # ROI calculators
│       └── tier.py / server_tier.py # Subscription tiers
├── frontend/
│   ├── index.html                 # Main SPA (984 lines)
│   ├── app.js                     # 8,527 lines — ALL frontend logic
│   ├── admin.html                 # Admin dashboard (689 lines)
│   ├── styles.css                 # All CSS
│   └── config.js                  # Frontend config
├── mobile/
│   ├── App.js                     # React Native WebView + push notifications
│   └── app.json                   # Expo config
├── tests/                         # 52 test files, 576 tests
├── CODEX_REVIEW.md                # Technical review document
└── sitenoladge.md                 # This file — complete knowledge base
```

---

## KNOWN ISSUES TO FIX

### CRITICAL (Must Fix)
1. **No rate limiting** on `/api/register` — OTP spam possible
2. **No auth guard on `/admin.html`** — Anyone can access admin
3. **No CSRF protection** on POST endpoints
4. **Service Worker fails** in dev (sw.js doesn't exist)

### HIGH PRIORITY
5. **app.js is 8,500 lines** — Needs modularization
6. **No WebSocket** for real-time search progress (uses polling)
7. **External scrapers are fragile** — HTML changes break them
8. **Mobile app not tested** — npm install fails (disk space)
9. **supabase_store.py uses raw HTTP** — No connection pooling

### WHAT THE USER NEEDS FROM CODEX
1. Add listing status management (Active/Pending/Rejected/Archived) — like the screenshot
2. Add listing approval workflow (Approve/Sold/Delete/Edit buttons)
3. Add property photos to admin listings
4. Add agent details (name, phone, type) to each listing card
5. Add statistics cards (agents count, listings count, views)
6. Fix rate limiting on OTP endpoint
7. Add auth guard to admin dashboard
8. Modularize app.js into components
9. Add real WebSocket for search progress
10. Set up proper production deployment

---

## EXTERNAL APIS & SERVICES

| Service | Purpose | Status | Needs Setup |
|---------|---------|--------|-------------|
| **Supabase** | Database | ✅ Configured | No |
| **WhatsApp Meta API** | OTP delivery | ✅ Configured | No |
| **Google Sign-In** | OAuth login | ❌ Not configured | YES — needs GOOGLE_CLIENT_ID |
| **FreeLLMAPI** | AI provider | ⚠️ Not running locally | Optional |
| **Ollama** | Local AI | ⚠️ Not installed | Optional |
| **Gemini** | Google AI | ❌ No API key | Optional |
| **OpenRouter** | Cloud AI | ❌ No API key | Optional |
| **Expo** | Mobile push | ⚠️ No project ID | Optional |

### ACTION ITEMS FOR USER
1. **Google Cloud Project**: Go to console.cloud.google.com → Create project → Enable Google Identity Services → Create OAuth 2.0 Client ID → Set GOOGLE_CLIENT_ID in .env
2. **FreeLLMAPI (optional)**: git clone https://github.com/tashfeenahmed/freellmapi → docker compose up -d → Get key from dashboard
3. **Production Domain**: Configure HTTPS, set up reverse proxy (nginx)
4. **Mobile App**: cd mobile → npm install → npx expo start → Scan QR with Expo Go

---

## PERFORMANCE METRICS

| Metric | Before | After |
|--------|--------|-------|
| Lighthouse Performance | 31/100 | 50/100 |
| First Contentful Paint | 7.2s | 3.6s |
| Largest Contentful Paint | 11.6s | 7.0s |
| Total Blocking Time | 1700ms | 718ms |
| Speed Index | 7.2s | 3.7s |
| Test Suite | 576 passed | 576 passed |
| Search Speed (fast) | 47s | 3.1s |
| API Endpoints | 50+ | 50+ |

---

## GIT HISTORY (Last 15 commits)

```
e97eae1 docs: comprehensive platform documentation for Codex review
93162ce fix: final review fixes — API endpoints, admin dashboard
f773944 feat(admin): professional admin dashboard
10260a1 perf: lazy-load Leaflet.js and Chart.js (50% faster)
be38152 feat(mobile): React Native Expo app + push notifications
08b24f0 fix(price-trends): median_price fallback
2a7fbad feat: interactive Leaflet.js map
0df878c perf: search speed 47s → 3s
8687931 docs: competitive analysis
f0fb869 feat: FreeLLMAPI integration
fcac43d fix: 4Sale/Bu3qar sources restored
ba47cf1 fix: hide Google button when unconfigured
b15b687 feat: multi-provider AI router
1a91c7e fix: search without login
a02a2ed fix: OTP registration hang
```

---

## COMPETITIVE ADMIN FEATURES (From Screenshot)

The production admin at search.alforaij.com has features we're missing:

### 1. Listing Status Management
- **الإعلانات النشطة (198)** — Active listings
- **إحصائيات الإعلانات** — Statistics: Total Agents (0), Total Views (0)
- **مرفوضة (1)** — Rejected
- **تمت الموافقة (196)** — Approved
- **فيdictions المراجعة (1)** — Pending review
- **مؤرشفة (117)** — Archived

### 2. Transaction Type Filters
- **للبيع** — For Sale
- **للايجار** — For Rent
- **شاليه للايجار** — Chalet for Rent
- **شاليه** — Chalet
- **جميع الأنواع** — All Types

### 3. Listing Card Features
Each listing card shows:
- Property photo (or placeholder)
- Area + Governorate
- Property type (أرض/عقارات)
- Price (السعر: 0 د.ك)
- Transaction type (نوع المعاملة: البيع)
- Published date
- Agent details (المعلن oficial, المهنة, المنطقة, هاتف المعلن)
- Action buttons: عرض التفاصيل, تسجيل صور, تعديل, حذف, تم البيع, موافق, رفض

### 4. Sidebar Navigation
- القائمة → الإعلانات, الصفحة الرئيسية
- قائمة الإدارة → الوكلاء, الموظفين, التحليلات, التقارير, التنبيهات
- إدارة الإعلانات → إدارة الإعلانات, تسجيل الخروج

### 5. Search & Filters
- Search by code or keywords
- Filter by company (جميع الشركات)
- Filter by listing type (جميع الإعلانات)
- Checkbox: خارج البيع (Outside sale)

---

## WHAT TO ASK CODEX TO DO

When giving this file to Codex, use this prompt:

```
 CODEX AGENT INSTRUCTIONS:
 
 You have full access to the Al-Furaj Real Estate Platform codebase.
 Read sitenoladge.md thoroughly. Then:
 
 1. REVIEW the entire codebase for bugs, security issues, and improvements
 2. ADD listing status management to admin dashboard (Active/Pending/Rejected/Archived)
 3. ADD listing approval workflow buttons (Approve/Sold/Delete/Edit)
 4. ADD property photos and agent details to admin listings
 5. ADD statistics cards (agents count, listings count, views)
 6. FIX rate limiting on OTP endpoint
 7. ADD auth guard to admin dashboard (admin-only access)
 8. SUGGEST how to modularize the 8,500-line app.js
 9. IDENTIFY any API keys or services that need user setup
 10. CREATE a production deployment plan
 
 The user has given you full device access. Make all changes directly.
 Test everything before committing. Push to GitHub when done.
```

---

*Generated: 2026-08-29 | Platform Version: 1.0 | Tests: 576 passed | APIs: 50+ | Sources: 18+*
*This file is the single source of truth for the Al-Furaj platform.*
