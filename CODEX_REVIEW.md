# دليل المنصة الشامل — منصة الفريج للفرص والتقييم العقاري

> **Purpose**: This document provides a complete technical overview of the Al-Furaj Real Estate Platform for AI code review agents (Codex, Claude, etc.) to understand the architecture, identify issues, and suggest improvements.

---

## 1. Project Overview

**Al-Furaj (الفريج)** is a Kuwait real estate research, evaluation, and opportunity platform that:

- Aggregates listings from 18+ external sources (4Sale, Mourjan, OpenSooq, FindQ8, etc.) plus 182 internal listings
- Provides AI-powered search with natural Arabic language queries ("بيت 400م في الفردوس")
- Evaluates properties with scoring, comparables, and investment recommendations
- Detects investment opportunities (price below market = "لقطة")
- Offers a chat assistant, PDF reports, and a React Native mobile app

**Live URL**: https://search.alforaij.com (production)  
**GitHub**: https://github.com/ahmedkamalsa/alforaij  
**Database**: Supabase (PostgreSQL) — 14 tables, 72,486 evidence records, 3,024 total listings  

---

## 2. Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Backend** | Python 3.13, stdlib `http.server` | No framework (no FastAPI/Flask) |
| **Frontend** | Vanilla JS (8,500 lines), HTML, CSS | No React/Vue — single `app.js` |
| **Database** | Supabase (PostgreSQL) | 14 tables, REST API |
| **Mobile** | React Native (Expo) | WebView wrapper + push notifications |
| **AI** | Multi-provider router (Ollama/Gemini/OpenRouter/FreeLLMAPI) | Fallback chain |
| **Testing** | pytest (576 tests) | Unit + integration |
| **CI/CD** | GitHub Actions | Build & deploy |
| **Hosting** | Local / Netlify (static) / Vercel | Backend runs locally |
| **Charts** | Chart.js (lazy-loaded) | Price trends |
| **Maps** | Leaflet.js + OpenStreetMap (lazy-loaded) | Property locations |

---

## 3. File Structure

```
alforaij-research-assistant/
├── backend/
│   ├── main.py                    # HTTP server + 50+ API endpoints (2,041 lines)
│   ├── config.py                  # Environment config, logging
│   ├── connectors/
│   │   ├── live_sources.py        # Scrapers: 4Sale, Mourjan, OpenSooq, FindQ8, etc.
│   │   ├── external_search.py     # External source search coordinator
│   │   ├── alforaij.py            # Internal Al-Furaj scraper
│   │   ├── alhisba_public.py      # Al-Hisba public data
│   │   ├── market_ads.py          # Market ad scraping
│   │   ├── official_data.py       # Government official data
│   │   └── official_indicators.py # Official market indicators
│   └── services/
│       ├── accounts.py            # OTP auth, roles (admin/employee/user), phone normalization
│       ├── supabase_store.py      # All database operations (1,225 lines)
│       ├── ai_evaluator.py        # AI-powered property evaluation
│       ├── ai_router.py           # Multi-provider AI with fallback chain
│       ├── request_parser.py      # Arabic NLP parser (extracts area/price/type from queries)
│       ├── valuation.py           # Property valuation logic
│       ├── opportunities.py       # Investment opportunity detection
│       ├── search_matching.py     # Search-result matching and scoring
│       ├── chat_agents.py         # Chat assistant with domain knowledge
│       ├── push_notifications.py  # Push notification service (Expo)
│       ├── pdf_report.py          # PDF report generation
│       ├── investment_calculator.py # ROI/mortgage calculators
│       ├── tier.py / server_tier.py # Subscription tiers
│       ├── admin_analytics.py     # Admin dashboard data
│       ├── source_registry.py     # Source management
│       ├── deduplication.py       # Listing dedup
│       ├── listing_classifier.py  # Property classification
│       └── ... (37 service files total)
├── frontend/
│   ├── index.html                 # Main SPA (984 lines)
│   ├── app.js                     # Main application logic (8,527 lines)
│   ├── styles.css                 # All styles
│   ├── admin.html                 # Admin dashboard (689 lines)
│   ├── config.js                  # Frontend config
│   ├── components/                # UI components
│   └── assets/                    # Images, icons
├── mobile/
│   ├── App.js                     # React Native WebView wrapper + push notifications
│   ├── app.json                   # Expo config
│   └── src/notifications.js       # Notification bridge
├── tests/                         # 52 test files, 576 tests
├── data/                          # JSON data files
├── docs/                          # Documentation
├── scripts/                       # Utility scripts
└── supabase/                      # Database migrations
```

---

## 4. API Endpoints (50+)

### GET Endpoints
| Endpoint | Description | Auth |
|----------|-------------|------|
| `/api/health` | Server health + data summary | No |
| `/api/google-client-id` | Google OAuth client ID | No |
| `/api/analytics` | Platform analytics | No |
| `/api/analytics-dashboard` | Analytics dashboard data | No |
| `/api/sources` | Available data sources | No |
| `/api/search-options` | Search filter options | No |
| `/api/market-analytics` | Market analysis data | No |
| `/api/market-insights` | Market insights | No |
| `/api/market-demand` | Supply/demand data | No |
| `/api/dashboard/summary` | Dashboard summary (listings, opportunities) | No |
| `/api/opportunities` | Investment opportunities list | No |
| `/api/opportunities/history` | Opportunity history | No |
| `/api/price-trends?area=X` | Price trends by area (583 records) | No |
| `/api/market-matching` | Supply/demand matching | No |
| `/api/live-db` | Live database status | No |
| `/api/roles` | User roles and permissions | No |
| `/api/ai/providers` | AI provider status | No |
| `/api/admin/users` | All registered users | Admin |
| `/api/push/stats` | Push notification statistics | No |
| `/api/update-notifications` | Platform update notifications | No |
| `/api/developments` | Market developments | No |
| `/api/whatsapp-alerts` | WhatsApp alert messages | No |
| `/api/outreach/stats` | Outreach click statistics | No |
| `/api/clients` | Client leads with WhatsApp links | No |
| `/api/metric-registry` | Metrics documentation | No |
| `/api/platform-dates` | Platform important dates | No |
| `/api/official-reference-sources` | Official government sources | No |

### POST Endpoints
| Endpoint | Description | Auth |
|----------|-------------|------|
| `/api/analyze` | **Main search endpoint** — query + evaluate + score | Optional |
| `/api/parse` | Parse natural language query to structured filters | No |
| `/api/whatsapp/parse` | Parse WhatsApp messages | No |
| `/api/register` | Phone number registration (OTP) | No |
| `/api/verify-otp` | Verify OTP code | No |
| `/api/google-login` | Google Sign-In (JWT verify) | No |
| `/api/report-pdf` | Generate PDF report | Optional |
| `/api/outreach-click` | Track outreach clicks | No |
| `/api/daily-agent/run` | Trigger daily data collection | Admin |
| `/api/official-transactions/import` | Import official transactions | Admin |
| `/api/tier/status` | Get user tier status | Token |
| `/api/tier/upgrade` | Upgrade user tier | Token |
| `/api/tier/authorize` | Authorize feature access | Token |
| `/api/tier/pricing` | Display pricing plans | No |
| `/api/admin/dashboard` | Admin dashboard analytics | Pro/Enterprise |
| `/api/invest/calculate` | ROI calculator | No |
| `/api/invest/mortgage` | Mortgage calculator | No |
| `/api/invest/compare` | Investment comparison | No |
| `/api/invest/forecast` | Investment forecast | No |
| `/api/classifiers` | Property classifiers | No |
| `/api/classify` | Classify listings | No |
| `/api/roles` | Roles and permissions | No |
| `/api/user/role` | Get/set user role | Token |
| `/api/user/role/check` | Check permission | Token |
| `/api/tiers` | List subscription tiers | No |
| `/api/push/register` | Register push token | No |
| `/api/push/subscribe` | Subscribe to notifications | No |
| `/api/push/unsubscribe` | Unsubscribe | No |
| `/api/push/send` | Send push notification | No |

---

## 5. Database Schema (Supabase)

### Tables
| Table | Records | Description |
|-------|---------|-------------|
| `listings` | 182 | Internal Al-Furaj property listings |
| `market_listings` | 2,824 | External market listings from all sources |
| `price_trends` | 583 | Monthly median prices by area/type |
| `market_ads` | 18 | Live market ads |
| `official_transactions` | 0 | Official government transactions (empty) |
| `official_market_indicators` | 53 | Official price indicators |
| `saved_reports` | 738 | Saved search reports |
| `source_runs` | 5,637 | Source execution logs |
| `listing_evidence` | 72,486 | Evidence for each number in results |
| `client_leads` | 1 | Client leads |
| `client_property_requests` | 0 | Property requests from display boards |
| `opportunities` | 407 | Investment opportunities |
| `search_history` | 471 | Search history records |
| `users` | ~5 | Registered users (phone + role + OTP) |

### Key Columns in `users` table
- `phone` (text, primary key) — normalized E.164 format
- `role` (text) — "admin" / "employee" / "user"
- `otp_hash` (text) — SHA256 hash of OTP
- `otp_expires_at` (timestamp)
- `otp_attempts` (integer)
- `created_at` (timestamp)

---

## 6. Authentication System

### Phone + OTP
1. User enters phone with country code (supports KW, SA, AE, BH, OM, QA, EG + 20 more)
2. Backend generates 6-digit OTP, hashes with SHA256, stores in Supabase
3. OTP sent via WhatsApp (Meta Cloud API) — falls back to console log in dev
4. User enters OTP, backend verifies hash + expiry + attempts
5. On success, returns a `user_secret` (24-char random) stored in localStorage

### Google Sign-In (partially implemented)
- Frontend loads Google Identity Services SDK
- On Google login, sends JWT credential to `/api/google-login`
- Backend verifies JWT, creates/updates user in Supabase
- **NOTE**: `GOOGLE_CLIENT_ID` env var not configured yet — button is hidden when empty

### Role-Based Access
```
admin:    Full access (all permissions)
employee: search, comparisons, dashboard_view, basic_analysis, pdf_reports, opportunity_alerts
user:     search, dashboard_view
```

---

## 7. AI System

### Multi-Provider Router (`ai_router.py`)
Fallback chain: FreeLLMAPI → Ollama → Gemini → OpenRouter → AgentRouter

| Provider | Type | Cost | Speed |
|----------|------|------|-------|
| FreeLLMAPI | Gateway | Free (34 providers) | Medium |
| Ollama | Local | Free, unlimited | Fast (1-3s) |
| Gemini | Google | Free 1M tokens/day | Medium |
| OpenRouter | Cloud | Free tier models | Medium |
| AgentRouter | Existing | Limited | Slow |

### How it works:
1. User sends search query → `request_parser.py` extracts area/price/type in Arabic
2. Backend searches local DB + external sources in parallel
3. `ai_evaluator.py` scores each result (matchScore, recommendationScore, dealScore)
4. Results ranked by score with evidence and comparables

---

## 8. Frontend Architecture

### Main Site (`index.html` + `app.js`)
- **Single-page app** with tab navigation (بحث، فرص، السوق، تحديثات، تحليلات، حساب)
- **8,527 lines** of vanilla JavaScript
- **Features**: Search, results with scoring, map, price trends chart, ROI calculator, chat assistant, PDF export, JSON export, saved searches, dark/light mode
- **Libraries**: Leaflet.js (map, lazy-loaded), Chart.js (charts, lazy-loaded)

### Admin Dashboard (`admin.html`)
- **689 lines** of HTML/CSS/JS
- **Sections**: Overview stats, Users, Roles & Permissions, Listings, Agents, Analytics, Market, Settings
- **Mobile responsive** with hamburger menu

### Performance (Lighthouse)
- Performance: 50/100 (was 31 — lazy loading improved by 61%)
- Accessibility: 92/100
- Best Practices: 100/100
- SEO: 100/100
- FCP: 3.6s (was 7.2s)
- TBT: 718ms (was 1700ms)

---

## 9. Testing

### Test Suite (576 tests)
```bash
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 python -m pytest tests/ -x --tb=short -q
```

### Key test files:
| File | Tests | Coverage |
|------|-------|----------|
| `test_accounts.py` | 15 | OTP, phone normalization, roles |
| `test_ai_router.py` | 18 | AI provider fallback chain |
| `test_request_parser.py` | 40+ | Arabic NLP parsing |
| `test_live_sources.py` | 57 | External source scrapers |
| `test_analysis.py` | 30+ | Search and evaluation |
| `test_api.py` | 20+ | API endpoint testing |
| `test_opportunities.py` | 15+ | Opportunity detection |
| `test_valuation.py` | 10+ | Property valuation |

---

## 10. Configuration

### Environment Variables (`.env`)
```
# Server
ALFORAIJ_ASSISTANT_HOST=127.0.0.1
ALFORAIJ_ASSISTANT_PORT=8000

# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx

# Google Sign-In
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com

# WhatsApp (optional)
WHATSAPP_TOKEN=xxx
WHATSAPP_PHONE_ID=xxx

# AI Providers (at least one needed)
FREELLMAPI_URL=http://127.0.0.1:5050/v1
FREELLMAPI_KEY=xxx
OLLAMA_URL=http://127.0.0.1:11434
GEMINI_API_KEY=xxx
OPENROUTER_API_KEY=xxx
```

### Running locally
```bash
# Install dependencies
pip install -r requirements.txt

# Start server
python -m backend.main

# Run tests
python -m pytest tests/ -x -q
```

---

## 11. Known Issues & Technical Debt

### Critical
1. **No rate limiting on `/api/register`** — anyone can spam OTP sends
2. **`/api/analyze` without auth gives unlimited searches** — tier system exists but isn't enforced for "all" mode
3. **No HTTPS** — local dev only, needs reverse proxy for production
4. **Service Worker registration fails** in dev (sw.js doesn't exist)

### High Priority
5. **Single 8,500-line `app.js`** — needs modularization into components
6. **No CSRF protection** on POST endpoints
7. **`supabase_store.py` uses raw HTTP** — no connection pooling, no retry logic
8. **External source scrapers are fragile** — HTML structure changes break them
9. **No WebSocket** for real-time search progress (uses polling)
10. **Mobile app not tested** — `npm install` fails due to disk space

### Medium Priority
11. **Admin dashboard has no auth guard** — anyone can access `/admin.html`
12. **Price trends chart shows 0 when only 1 month of data**
13. **No data validation** on API inputs (trusts all client data)
14. **No structured logging** — just `print` and basic `logging`
15. **No API versioning** — all endpoints at `/api/`

### Low Priority
16. **`whatsapp.html` was deleted** but still referenced in some configs
17. **Unused files**: `New DOC Document.doc`, `Vibe_Coding_AI_Business_System_Presentation.pptx`
18. **No Swagger/OpenAPI docs** for the API
19. **No health check for external sources** (Sakan times out at 30s)
20. **`request_parser.py`** could use better handling of mixed Arabic/English numbers

---

## 12. Competitor Analysis Summary

| Feature | Bayut | PropertyFinder | Sakan | **Al-Furaj** |
|---------|-------|----------------|-------|-------------|
| Arabic NLP search | ❌ | ❌ | ❌ | ✅ |
| 18 sources in one search | ❌ | ❌ | ❌ | ✅ |
| AI evaluation + scoring | ✅ | ✅ | ❌ | ✅ |
| Official transactions | ❌ | ❌ | ❌ | ✅ |
| Free forever | ❌ | ❌ | Partial | ✅ |
| Investment opportunity detection | ❌ | ❌ | ❌ | ✅ |
| Interactive map | ✅ | ✅ | ❌ | ✅ |
| Mobile app | ✅ | ✅ | ✅ | ✅ (new) |
| PDF/Excel reports | Paid | Paid | ❌ | ✅ Free |
| Price trends by area | ✅ (UAE only) | ✅ (UAE only) | Partial | ✅ (Kuwait) |

---

## 13. What to Review

Please focus your review on:

1. **Architecture** — Is the stdlib http.server approach sustainable? Should we migrate to FastAPI?
2. **Security** — Authentication gaps, input validation, rate limiting
3. **Performance** — Search speed (3s fast mode, 47s full mode), database queries
4. **Code Quality** — `app.js` is 8,500 lines; `main.py` is 2,041 lines. How to modularize?
5. **Scalability** — Will this work with 10,000+ users?
6. **Testing** — Are 576 tests sufficient? What's missing?
7. **Deployment** — Currently local-only. What's needed for production?
8. **Mobile** — React Native WebView approach vs. native rebuild?
9. **AI Integration** — Is the fallback chain the right approach? Should we use RAG?
10. **Data Quality** — How reliable are the scrapers? How often does data go stale?

---

## 14. Git History (Last 30 commits)

```
93162ce fix: final review fixes — API endpoints, admin dashboard, search
f773944 feat(admin): add professional admin dashboard
10260a1 perf: lazy-load Leaflet.js and Chart.js (50% faster FCP)
be38152 feat(mobile): React Native Expo app with push notifications
08b24f0 fix(price-trends): median_price fallback
2a7fbad feat: interactive Leaflet.js map
0df878c perf: search speed 47s → 3s
8687931 docs: competitive analysis
f0fb869 feat: FreeLLMAPI integration
fcac43d fix: 4Sale/Bu3qar sources restored
ba47cf1 fix: hide Google button when unconfigured
69ef725 test: 18 AI Router tests
b15b687 feat: multi-provider AI router
1a91c7e fix: search without login
a02a2ed fix: OTP registration hang
```

---

*Generated: 2026-08-29 | Platform Version: 1.0 | Tests: 576 passed | APIs: 50+ | Sources: 18+*
