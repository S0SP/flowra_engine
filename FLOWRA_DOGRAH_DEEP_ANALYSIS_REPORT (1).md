# Flowra + Dograh: Full Deep Analysis Report

**Date:** August 2026  
**Stack:** Next.js (Vercel Free) · Django + Celery (Google Cloud $300 free) · Dograh OSS (FastAPI + Pipecat) · Supabase · Trigger.dev · Razorpay (Test) · Gemini Live Preview API

---

## TABLE OF CONTENTS

1. [Project Architecture Overview](#1-project-architecture-overview)
2. [Dograh OSS Deep Analysis](#2-dograh-oss-deep-analysis)
   - 2A. Voicelink → Vobiz Migration Status
   - 2B. Gemini Live Integration Status
   - 2C. What is Mocked vs Real in Dograh
3. [Flowra Engine Deep Analysis](#3-flowra-engine-deep-analysis)
4. [Flowra Frontend Deep Analysis — All Features](#4-flowra-frontend-deep-analysis--all-features)
   - Dashboard
   - Shared Inbox
   - Tickets
   - Contacts & Leads CRM
   - Workflows
   - Campaigns
   - Broadcasts
   - Lead Capture
   - AI Chatbot
   - Voice Agent
   - Knowledge Base
   - Analytics
   - Team
   - Settings
   - Billing & Checkout
5. [Critical Issues & Security Exposures](#5-critical-issues--security-exposures)
6. [Deployment Configuration Review](#6-deployment-configuration-review)
7. [What Needs to Be Fixed Before Deploy](#7-what-needs-to-be-fixed-before-deploy)
8. [Full File Inventory with Status](#8-full-file-inventory-with-status)

---

## 1. PROJECT ARCHITECTURE OVERVIEW

Your stack has three separate codebases that talk to each other:

```
                    ┌─────────────────────────┐
  Users ──────────► │  Flowra Frontend         │  (Next.js 14 App Router)
                    │  Deployed: Vercel Free   │  vercel.json → region: bom1
                    └────────┬────────────────┘
                             │ Supabase (DB + Auth + Realtime)
                             │ Internal Next.js API routes
                             │
                             ├─────────────────────────────────────────►
                             │                                 ┌──────────────────────┐
                             │                                 │  Flowra Engine       │
                             │  REST (DOGRAH_API_URL)          │  Django + Celery     │
                             │◄──────────────────────────────► │  Google Cloud Free   │
                             │                                 │  Polls sheets, runs  │
                             │                                 │  workflows, billing  │
                             │                                 └──────────────────────┘
                             │
                             │  POST /api/v1/telephony/initiate-call
                             │  Header: X-Flowra-Secret
                             ▼
                    ┌─────────────────────────┐
                    │  Dograh OSS (FastAPI)    │  ai.voice.orchestration
                    │  Pipecat pipelines       │  Google Cloud Free
                    │  Telephony: Vobiz        │
                    │  AI: Gemini Live         │
                    └─────────────────────────┘
```

**Key shared credentials:**
- Supabase: `kgdlmgtslhjpytncxwzw.supabase.co` — shared between Frontend and Engine
- Redis: Upstash (`devoted-chimp-139022.upstash.io`) — shared Frontend + Engine
- Secret handshake: `FLOWRA_SECRET=sumit` / `DOGRAH_SECRET=sumit` — **INSECURE, must change**
- Gemini API Key: `AIzaSyBxIgY0CZIuRsyGItKCCOy65W5r9T2ZFaE` — shared across all three

---

## 2. DOGRAH OSS DEEP ANALYSIS

### 2A. Voicelink → Vobiz Migration Status

#### Current State (Voicelink Plugin — What Exists)

The Dograh codebase **already has a fully implemented Vobiz provider** sitting alongside VoiceLink. Both providers are fully registered and functional at the code level. The migration is NOT a code-change task — it is a **configuration + database task**.

**VoiceLink Provider Files (currently in use / was the default):**
| File | Path in dograh.zip | Status |
|---|---|---|
| `__init__.py` | `api/services/telephony/providers/voicelink/__init__.py` | Registered, active |
| `provider.py` | `api/services/telephony/providers/voicelink/provider.py` | Full impl — Plivo-style auth, token refresh, A-law 8kHz |
| `transport.py` | `api/services/telephony/providers/voicelink/transport.py` | FastAPI WebSocket |
| `serializers.py` | `api/services/telephony/providers/voicelink/serializers.py` | Frame serializer |
| `config.py` | `api/services/telephony/providers/voicelink/config.py` | Pydantic schemas |
| `routes.py` | `api/services/telephony/providers/voicelink/routes.py` | Webhook routes |

**Vobiz Provider Files (fully implemented, ready to use):**
| File | Path in dograh.zip | Status |
|---|---|---|
| `__init__.py` | `api/services/telephony/providers/vobiz/__init__.py` | ✅ Registered via `register(SPEC)` |
| `provider.py` | `api/services/telephony/providers/vobiz/provider.py` | ✅ Full impl — Plivo-compatible API, JSON body, MULAW 8kHz |
| `transport.py` | `api/services/telephony/providers/vobiz/transport.py` | ✅ FastAPI WebSocket with realtime_param_overrides |
| `serializers.py` | `api/services/telephony/providers/vobiz/serializers.py` | ✅ VobizFrameSerializer |
| `config.py` | `api/services/telephony/providers/vobiz/config.py` | ✅ Pydantic — auth_id, auth_token, application_id, from_numbers |
| `routes.py` | `api/services/telephony/providers/vobiz/routes.py` | ✅ Webhook routes for inbound + hangup |

**How Vobiz works in Dograh (verified from code):**
- Uses `https://api.vobiz.ai/api` as base URL
- Auth via `X-Auth-ID` and `X-Auth-Token` headers
- Phone numbers in E.164 **without** `+` prefix
- Outbound: `POST /v1/Account/{auth_id}/Call/` with JSON body
- Hangup callback: `/api/v1/telephony/vobiz/hangup-callback/{workflow_run_id}`
- Ring callback: `/api/v1/telephony/vobiz/ring-callback/{workflow_run_id}`
- Auto-creates Vobiz Application on first save (if `application_id` not supplied)
- Inbound URL is set to: `{backend_endpoint}/api/v1/telephony/inbound/run`
- Audio: MULAW 8kHz (Plivo-compatible WebSocket protocol)
- DB enum `workflow_run_mode` already has `vobiz` value (migration `a188ff90e76f` applied)

**What you need to do to switch from VoiceLink to Vobiz:**

1. **In Dograh UI** → Settings → Telephony → Add New Configuration → Select "Vobiz"
   - Fill in: `auth_id` (Vobiz Account ID), `auth_token`, leave `application_id` blank (auto-creates)
   - Add phone numbers in E.164 without `+`
2. **Set Vobiz as the default telephony config** for your organization in Dograh
3. **In Flowra Frontend `.env`**: Remove `VOICELINK_SIP_TECH_PREFIX` and `LIVEKIT_*` keys (they're irrelevant now — Vobiz handles telephony, Dograh handles routing)
4. **In Dograh `.env`**: Add `VOBIZ_AUTH_ID` and `VOBIZ_AUTH_TOKEN` if you want env-level defaults (optional — the UI config is preferred)
5. Update `PUBLIC_BASE_URL` in Dograh's `.env` to your real Google Cloud URL (not the ngrok one)

**Gap/Issue:** The Flowra Frontend `settings/page.tsx` (line 448, 737-770) still shows a "Voice & Calling Configuration" panel with UI for **Dograh Phone Number** and a **Dograh Workflow ID** — it does NOT expose Vobiz credentials directly. That's by design because Vobiz credentials are managed inside Dograh's own UI, not Flowra's settings. The Flowra side only needs to know the Dograh API URL and the workflow ID to dispatch calls to. This is correct architecture.

**What is still wired to LiveKit (needs cleanup):**
- `src/lib/livekit.ts` — LiveKit SDK is imported and creates SIP client, room service, agent dispatch. This is the OLD architecture where Dograh dispatched LiveKit rooms. **Since you're moving to Vobiz (Dograh handles SIP natively), this file becomes unused for telephony.** However, it still references `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` from env.
- `src/services/voice.ts` — `initiateVoiceCall()` now correctly calls `${dograhUrl}/api/v1/telephony/initiate-call` directly without going through LiveKit. ✅ This is correct.
- `src/app/dashboard/voice-agent/page.tsx` line 448 — still shows a toast message referencing "LiveKit" and "Voicelink" stuck SIP sessions. This is stale UI copy that needs updating.
- `src/app/dashboard/settings/page.tsx` lines 82-84 — still has state variables `livekitUrl`, `livekitApiKey`, `livekitApiSecret` but they're only saved if non-empty (lines 460-464). These fields exist in the UI but are now irrelevant if Vobiz is the telephony provider.

---

### 2B. Gemini Live Integration Status

**Gemini Live is already connected end-to-end.** Here is the exact flow:

1. **Flowra Frontend** → `src/services/voice.ts` `initiateVoiceCall()`:
   - When `agentType === "gemini"`, builds `model_overrides` with `provider: "google_realtime"` and passes it in `initial_context` to Dograh's `/api/v1/telephony/initiate-call`

2. **Dograh** → `api/services/pipecat/service_factory.py`:
   - Has `_migrate_deprecated_google_realtime_model()` function
   - `api/services/configuration/registry.py` has `GOOGLE_REALTIME = "google_realtime"` as a registered realtime provider
   - The workflow executor in Dograh reads `model_overrides.is_realtime = true` and `realtime.provider = "google_realtime"` and routes accordingly

3. **Gemini API Key**: `AIzaSyBxIgY0CZIuRsyGItKCCOy65W5r9T2ZFaE` is set in Dograh `.env` as `GEMINI_API_KEY` ✅

**Issues with Gemini Live setup:**
- `GEMINI_LIVE_MODEL=gemini-2.0-flash-exp` is set in Flowra Frontend `.env` but the model referenced in the code is the **Preview API** (`gemini-2.0-flash-exp` was the old name). The current correct model name for Gemini Live Preview API is `gemini-2.0-flash-live-001` or `gemini-live-2.5-flash-preview`. **You need to confirm the correct model string** from Google's latest Preview API docs and update both Flowra Frontend and Dograh's AI configuration.
- Voice IDs in `src/services/voice.ts` — the `sanitizeGeminiLiveVoice()` function correctly falls back unsupported Gemini voices (all the Sarvam names) to the 5 supported Gemini Live voices: `Puck`, `Charon`, `Kore`, `Fenrir`, `Aoede`. This is correct.
- The voice selector UI in `src/app/dashboard/voice-agent/page.tsx` shows all 30+ Gemini voice names (including `Zephyr`, `Achernar`, etc.) from the WAV files in `public/voices/gemini/` — but Gemini Live API only supports 5. The UI selection works but the runtime will silently remap to one of the 5. This should be surfaced to the user.

---

### 2C. What is Mocked vs Real in Dograh

| Component | Status | Notes |
|---|---|---|
| VoiceLink Provider | ✅ Real (was production) | Complete implementation |
| Vobiz Provider | ✅ Real (code complete) | Needs credentials in UI config |
| Gemini Live (google_realtime) | ✅ Real | Connected via `GEMINI_API_KEY` |
| Workflow Builder | ✅ Real | Full node-based flow |
| Campaign runner | ✅ Real | Runs workflows against contact lists |
| Knowledge Base / RAG | ✅ Real | pgvector + embeddings |
| MCP Server | ✅ Real | FastAPI MCP with workflow tools |
| Auth | ✅ Real | OSS JWT or Stack Auth |
| Pipecat pipeline | ✅ Real | Full audio pipeline, noise cancellation (RNNoise) |
| Billing/Quotas | ✅ Real | Quota tables, usage tracking |
| S3 Audio Storage | ✅ Real | Configured with Cloudflare R2 |
| TURN Server | ⚠️ Dev only | Uses `localhost` — needs real TURN in prod |
| FLOWRA_SECRET | ❌ Insecure | Set to `"sumit"` — must be changed |
| OpenAI API Key | ❌ Missing | `.env` shows `sk-...` placeholder |

---

## 3. FLOWRA ENGINE DEEP ANALYSIS

**Location:** `flowra_engine.zip` — Django + Celery application

### Architecture
- Django REST Framework, no user auth (engine-secret auth only)
- Connects to the **same Supabase PostgreSQL DB** as the frontend using `managed = False` models
- Celery with Upstash Redis for background tasks
- `ALLOWED_HOSTS = ['*']` — **insecure for production**

### What Works (Connected & Real)

| Component | File | Status |
|---|---|---|
| Workflow Execution Engine | `executor/engine.py` | ✅ Real — WhatsApp, Email, Voice, Conditions, Loops |
| WhatsApp Message Sending | `executor/engine.py::send_whatsapp_message()` | ✅ Real — Meta API with workspace-specific creds |
| SMTP Email | `executor/engine.py::send_smtp_email()` | ✅ Real — reads SMTP config from DB |
| Google Sheets Polling | `executor/tasks.py` | ✅ Real — polls every 60s via Celery Beat |
| Voice Call Dispatch | `executor/engine.py::initiate_dograh_voice_call()` | ✅ Real — calls Dograh API |
| Lead Capture Polling | `executor/tasks.py::async_poll_lead_campaigns()` | ✅ Real |
| DB Models | `executor/models.py` | ✅ `managed=False` — reads Supabase tables directly |
| AES-GCM Token Decryption | `executor/engine.py` | ✅ Real — decrypts encrypted WhatsApp tokens |

### What is Mocked / Broken

| Component | File | Issue |
|---|---|---|
| Razorpay Checkout | `executor/billing_views.py::RazorpayCheckoutView` | ❌ FULLY MOCKED — comment says "Mocking for now since we don't have the library installed" — generates fake order_id |
| Razorpay Webhook | `executor/billing_views.py::RazorpayWebhookView` | ❌ MOCKED — comment says "Basic signature verification mock" — no real Razorpay SDK |
| Coupon Validation | `executor/billing_views.py` | ❌ Reads from `Coupon` model but the Django app has no `Coupon` table defined in the migration — will 500 |
| Subscription Model | `executor/models.py` | ❌ `WorkspaceSubscription`, `AICreditLedger`, `AICreditTransaction` — referenced in billing_views but these models are not in `0001_initial.py` migration |
| Credit Tracking | `executor/models.py` | ❌ `AICreditLedger` and related — no migration, will fail |
| Debug=True in Production | `flowra_engine/settings.py` | ❌ `DEBUG = os.getenv('DEBUG', 'True')` defaults to True — `.env` has `DEBUG=True` |
| `SECRET_KEY=sumit` | `flowra_engine/.env` | ❌ Insecure default |
| `ENGINE_SECRET_KEY=sumit` | `flowra_engine/.env` | ❌ Cross-service secret is "sumit" |
| `DOGRAH_SECRET=change-me-in-production` | Used in engine | ❌ Not updated |
| `ALLOWED_HOSTS = ['*']` | `flowra_engine/settings.py` | ❌ Allows any host — set to actual Cloud Run domain |
| Celery Beat in dev | `flowra_engine/settings.py` | ⚠️ 60s polling — works but wasteful for free tier |

### Billing in Engine — Needs Complete Rebuild

The checkout flow hits `http://localhost:8000/executor/billing/checkout/` (hardcoded in `src/app/checkout/page.tsx`) — this will fail in production. The full billing system needs:
1. Add `razorpay` Python library to `requirements.txt`
2. Add `WorkspaceSubscription`, `Coupon`, `AICreditLedger` models to migration `0001_initial.py`
3. Implement real Razorpay order creation in `RazorpayCheckoutView`
4. Implement real HMAC signature verification in `RazorpayWebhookView`
5. Update hardcoded `localhost:8000` URL in checkout page to use env variable

---

## 4. FLOWRA FRONTEND DEEP ANALYSIS — ALL FEATURES

### 4.1 Dashboard (`src/app/dashboard/page.tsx`)

**Status: ✅ Connected & Real**

- Fetches real analytics from `/api/analytics` → `src/app/api/analytics/route.ts`
- Shows: Total Contacts, Open Conversations, Active Campaigns, Voice Calls (Monthly), Messages (7d), Delivery Rate, Bot Replies, Knowledge Chunks
- Real-time presence via `usePresence()` hook → Supabase realtime
- Quick Actions: Create Workflow, New Broadcast, Import Contacts, Start Voice Call, Update Knowledge, Configure Chatbot
- Role-based visibility (owner/admin/manager/agent)
- Area chart of daily message trend using Recharts

**What needs fixing:** None critical. The dashboard is production-ready.

---

### 4.2 Shared Inbox (`src/app/dashboard/inbox/page.tsx` + `src/components/chat/inbox-client.tsx`)

**Status: ✅ Connected — ⚠️ Some mock data residual**

**Real & Connected:**
- `/api/inbox/threads` — fetches real threads from Supabase `inbox_threads` table
- `/api/inbox/threads/[id]/messages` — real message fetch + send
- Real-time updates via `useInboxRealtime` hook → Supabase realtime channel subscriptions
- Thread assignment (`/api/inbox/assign`) — real, sends to Supabase
- Media upload (`/api/inbox/upload-media`) — real, uploads to Supabase Storage
- WhatsApp message sending — real via Meta API
- AI chatbot handoff — real
- Routing rules (`/api/inbox/routing`) — real

**What is mocked / incomplete:**
- `src/lib/api/mock-db.ts` — contains hardcoded `Contact[]`, `Thread[]`, `Message[]`, `Lead[]` data. This file is NOT used by the inbox page (which reads from Supabase) but may still be imported by legacy components. Needs audit to confirm nothing production-critical imports it.
- The inbox client (`src/components/chat/inbox-client.tsx`) is a separate component from the main inbox page — they appear to duplicate some logic.

---

### 4.3 Tickets (`src/app/dashboard/tickets/page.tsx` + `/api/tickets/`)

**Status: ✅ Connected & Real**

- CRUD via `/api/tickets/route.ts` → Supabase `tickets` table
- Ticket escalation: `/api/tickets/[id]/escalate/route.ts`
- Internal notes: `/api/tickets/[id]/notes/route.ts`
- Ticket detail view: `src/app/dashboard/tickets/[id]/page.tsx`
- Agent-specific ticket views with role-based filtering

**What needs fixing:** None critical. Fully connected.

---

### 4.4 Contacts (`src/app/dashboard/contacts/page.tsx`)

**Status: ✅ Connected & Real**

- Full CRUD via `/api/contacts/route.ts`
- Import from CSV/Excel — real (uses papaparse + XLSX)
- Contact sidebar with history: `src/components/contacts/contact-sidebar.tsx`
- Contact table with sorting/filtering: `src/components/contacts/contacts-table.tsx`
- Custom fields support via `custom_fields` JSONB column
- Tags system via migration `007_tags.sql`

**What needs fixing:** None critical.

---

### 4.5 Leads CRM (`src/app/dashboard/leads/page.tsx`)

**Status: ✅ Connected & Real — ⚠️ Some hardcoded columns**

- Kanban board: `src/components/organisms/KanbanBoard.tsx` — drag & drop with real Supabase updates
- Full CRUD via `/api/leads/route.ts`
- Custom fields schema via `010_custom_field_schemas.sql`
- Deal settings panel: `src/components/settings/DealsSettingsPanel.tsx`
- Tags & custom fields manager: `src/components/settings/TagsAndFieldsPanel.tsx`

**What needs fixing:**
- Some default stage names may be hardcoded in the frontend KanbanBoard component rather than being fully dynamic from DB

---

### 4.6 Workflows (`src/app/dashboard/workflows/page.tsx` + `builder/page.tsx`)

**Status: ✅ Connected & Real — ⚠️ Trigger.dev partially wired**

**Real & Connected:**
- Workflow list page with CRUD — `/api/workflows/route.ts` → Supabase `workflows` table
- Workflow builder — `src/app/dashboard/workflows/builder/page.tsx` (90KB — very large component)
- Visual canvas: `src/components/organisms/WorkflowCanvas.tsx` — React Flow canvas with custom nodes
- Template library: `src/lib/workflow-templates.ts` — 18KB of preset workflow templates
- In-process execution: `src/lib/workflow/executor.ts` — runs synchronously in Next.js API routes
- Trigger system: `src/lib/workflow/trigger.ts` — parses trigger conditions
- Reminder scheduling: `src/lib/workflow/reminders.ts`
- Workflow runs tracking: `/api/workflows/runs/route.ts`
- Google Sheets trigger fetch: `/api/workflows/fetch-sheet-headers/route.ts`

**Trigger.dev Integration:**
- `trigger.config.ts` — project `proj_tjulrzvrslkplxbjtnpv`, configured correctly
- `src/trigger/knowledge.ts` — real Trigger.dev task for async knowledge base processing
- `src/app/api/jobs/campaign-execute/route.ts` — Trigger.dev job route
- `src/app/api/jobs/workflow-step/route.ts` — Trigger.dev job route
- `TRIGGER_SECRET_KEY=tr_prod_Bzi5I8LyyFo4y5EMVeRa` — set in `.env` ✅

**What needs fixing:**
- `src/app/api/workflows/trigger/route.ts` — triggers workflow execution but still falls back to in-process execution for synchronous nodes. Long workflows on Vercel free plan face the 60-second function timeout limit. Celery-heavy workflows should be offloaded to Trigger.dev tasks.
- The workflow builder page is 90KB of code — should be split into components for maintainability, though it works as-is.
- `src/lib/qstash.ts` (5KB) — QStash integration exists but seems partially replaced by Trigger.dev. Needs audit — if Trigger.dev is the chosen queuing system, QStash should be removed to avoid confusion.

---

### 4.7 Campaigns (`src/app/dashboard/campaigns/page.tsx`)

**Status: ✅ Connected & Real**

- Campaign CRUD — `/api/campaigns/route.ts`
- Campaign sender component — `src/components/campaign/campaign-sender.tsx` (19KB)
- Scheduled campaigns — `/api/campaigns/schedule/route.ts`
- Queue processing — `/api/campaigns/process-queue/route.ts`
- Campaign executor — `src/lib/campaign/executor.ts` — real, sends WhatsApp templates
- Status badge component — `src/components/campaign/campaign-status-badge.tsx`

**What needs fixing:** The process-queue route (`src/app/api/campaigns/process-queue/route.ts`) appears to be a polling endpoint. On Vercel free plan, cron jobs have limitations — confirm Trigger.dev scheduled tasks handle campaign queue draining instead of relying on Vercel's cron.

---

### 4.8 Broadcasts (`src/app/dashboard/broadcasts/page.tsx`)

**Status: ✅ Connected & Real**

- Full broadcast CRUD with Supabase
- WhatsApp template selection
- Contact targeting with filters
- Scheduled broadcast support

**What needs fixing:** None critical. Confirm that broadcast sending goes through the same `sendWhatsAppTemplate` → Meta API path as campaigns.

---

### 4.9 Lead Capture (`src/app/dashboard/lead-capture/page.tsx`)

**Status: ✅ Connected & Real — ⚠️ UI is a redirect stub**

- The lead capture page (`src/app/dashboard/lead-capture/page.tsx`) is only 695 bytes — it's a thin wrapper that redirects to the actual component
- The real implementation is in `src/components/lead-capture/lead-capture-client.tsx` (90KB — massive component)
- `/api/lead-capture/route.ts` — real CRUD for lead capture settings
- `src/services/lead-capture.ts` — real service with Google Sheets fetching, WhatsApp template sending, email sending, voice call dispatch
- Multi-workflow support — `migration-lead-capture-multi-workflow.sql`

**What needs fixing:**
- The `src/app/dashboard/lead-capture/page.tsx` (695 bytes) just does `<LeadCaptureClient />` — confirm this renders correctly without needing wrapper logic
- The Lead Capture service in `src/services/lead-capture.ts` dispatches voice calls to Dograh. The `geminiLiveLanguage()` helper is defined here and in `src/services/voice.ts` — duplicated, should be extracted to shared util

---

### 4.10 AI Chatbot (`src/app/dashboard/chatbot/page.tsx`)

**Status: ✅ Connected & Real**

- Chatbot settings CRUD via `/api/chatbot/route.ts`
- Test chat interface via `/api/chatbot/test/route.ts`
- FAQ management — `/api/chatbot/faqs/route.ts`
- Gemini API integration — `src/services/ai.ts`
- Context caching — `src/services/gemini-cache.ts` (Gemini prompt caching)
- Function calling / tools — `check_lead_status`, `check_booking_status` tools defined
- Groq fallback — uses `groq_api_key` if Gemini key missing
- Web widget embed — `/api/widget/embed.js/route.ts` + `/api/widget/chat/route.ts` + `/api/widget/config/route.ts`
- Widget chat page — `src/app/widget/chat/page.tsx`

**What needs fixing:**
- Chatbot page is 83KB — extremely large single file. Works but is hard to maintain.
- `GROQ_API_KEY` is not set in `.env` — only `GEMINI_API_KEY` is. If Gemini fails, Groq fallback will also fail.
- `src/services/gemini-cache.ts` — Gemini context caching is implemented but uses the `v1beta` API endpoint which is Preview. Confirm this still works with your API key tier.

---

### 4.11 Voice Agent (`src/app/dashboard/voice-agent/page.tsx`)

**Status: ⚠️ Partially Connected — Needs Vobiz wiring**

**Real & Connected:**
- Dial pad UI with phone number input
- Agent type toggle: "Sarvam + Groq (livekit)" vs "Gemini Live"
- Voice selection from `src/lib/voices.ts` (30+ voices)
- Call initiation → `src/services/voice.ts::initiateVoiceCall()` → Dograh API ✅
- Call records fetching from Supabase `voice_calls` table
- Recording playback via Supabase signed URLs
- Cost breakdown display per call
- "Kill Stuck Calls" button — calls Dograh health endpoint

**Issues / What needs updating for Vobiz:**
- Line 448 in `page.tsx` shows toast: `"LiveKit clean. If Voicelink still blocks calls → check Voicelink admin panel"` — this copy references old providers. Update to say "Vobiz" and "Dograh".
- The voice agent type toggle still shows `"Sarvam + Groq"` for the non-Gemini option (line 685). This label reflects the AI stack (Sarvam TTS + Groq LLM), NOT the telephony provider. The telephony provider is now Vobiz. This is fine architecturally but confusing UX — the label should say "Sarvam TTS / Groq LLM" with a separate note that telephony is via Vobiz/Dograh.
- Gemini voice list in UI shows 30 voices from `public/voices/gemini/*.wav` — but only 5 are supported by Gemini Live API. The `sanitizeGeminiLiveVoice()` in `src/services/voice.ts` handles remapping at runtime, but users will be confused when their selected voice changes. Display only the 5 supported voices in the UI when Gemini is selected.
- `src/app/dashboard/voice-agent/voices/page.tsx` (15KB) — voice preview page where users can play WAV samples. Works for demonstration but all the non-supported Gemini Live voices will be remapped silently.
- `src/app/dashboard/voice-agent/calls/page.tsx` (19KB) — call history with cost breakdown. Fully connected to Supabase `voice_calls` table. ✅

**What still references LiveKit unnecessarily:**
- `src/lib/livekit.ts` — imports `SipClient`, `AgentDispatchClient`, `EgressClient` from `livekit-server-sdk`. These are dead code now that Dograh handles SIP via Vobiz. Keep the file only if you plan to re-use LiveKit for recording egress (the `EgressClient` could still be used to pull recordings from LiveKit rooms if any exist). Otherwise remove.
- `src/lib/livekit/normalize-url.ts` — normalizes wss:// to https://. Only needed if LiveKit is used.

---

### 4.12 Knowledge Base (`src/app/dashboard/knowledge/page.tsx`)

**Status: ✅ Connected & Real**

- Full CRUD for knowledge sources — `/api/knowledge/documents/route.ts`
- File upload — `/api/knowledge/upload/route.ts` → Supabase Storage `knowledge-files` bucket
- Query endpoint — `/api/knowledge/query/route.ts`
- RAG service — `src/services/rag.ts` — real vector similarity search via Supabase `match_knowledge_chunks` RPC
- Trigger.dev task — `src/trigger/knowledge.ts` — async knowledge processing with Gemini `text-embedding-004` embeddings
- URL scraping via TinyFish — `src/lib/tinyfish.ts` + `TINYFISH_API_KEY` set in `.env`
- Supports: PDF, DOCX, TXT, CSV, XLSX, MD, URL (via TinyFish scrape)

**What needs fixing:**
- `TINYFISH_API_KEY=sk-tinyfish-InXsYrE2Q_UVf-Z-qsS37nmFJfxr-ysl` — this is a live API key in the committed `.env`. Rotate before production.
- Knowledge page is 38KB — large but functional.

---

### 4.13 Analytics (`src/app/dashboard/analytics/page.tsx`)

**Status: ✅ Connected & Real**

- Full analytics dashboard — `/api/analytics/route.ts`
- Real Supabase queries: contacts, campaigns, messages, voice calls, knowledge chunks
- Charts via Recharts
- Loading skeleton: `src/app/dashboard/analytics/loading.tsx`

**What needs fixing:** None critical.

---

### 4.14 Team (`src/app/dashboard/team/page.tsx`)

**Status: ✅ Connected & Real**

- Team member management — `/api/team/route.ts` + `/api/workspace/members/route.ts`
- Invitation system — `/api/workspace/invitations/route.ts`
- Invite token flow — `/api/invite/[token]/accept/route.ts` + `/api/invite/[token]/peek/route.ts`
- Invite page — `src/app/invite/[token]/page.tsx`
- Presence dots — `src/components/presence/PresenceDot.tsx` + heartbeat `src/components/presence/PresenceHeartbeat.tsx`
- Role management (owner, admin, manager, agent)
- API key management — `/api/workspace/api-keys/route.ts`

**What needs fixing:** None critical.

---

### 4.15 Settings (`src/app/dashboard/settings/page.tsx`)

**Status: ⚠️ Mostly Connected — Several sections incomplete**

The settings page is 63KB and has these sections:

| Section | Status | Notes |
|---|---|---|
| General / Workspace | ✅ Real | Name, currency, timezone |
| WhatsApp | ✅ Real | Full Meta API integration, phone verification, WABA config |
| Voice & Calling | ⚠️ Partial | Saves to `channel_connections` with type=voice. UI shows Dograh workflow ID, phone. Doesn't expose Vobiz credentials (correct). LiveKit fields still present but optional. |
| Email / SMTP | ✅ Real | SMTP config with test endpoint `/api/settings/test-smtp` |
| AI Chatbot | ✅ Real | Gemini key, Groq key, LiveKit key stored per workspace |
| Templates | ✅ Real | WhatsApp template manager — `src/components/settings/TemplateManagerPanel.tsx` (38KB) |
| Tags & Custom Fields | ✅ Real | `src/components/settings/TagsAndFieldsPanel.tsx` |
| Deal Stages | ✅ Real | `src/components/settings/DealsSettingsPanel.tsx` |
| Integrations page | ⚠️ Stub | `src/app/dashboard/integrations/page.tsx` is only 171 bytes — `"Coming soon"` |
| Billing | ⚠️ Incomplete | See Section 4.16 |

**WhatsApp integration files (all real):**
- `src/lib/whatsapp/meta-api.ts` — verifyPhoneNumber, registerPhoneNumber, sendText, sendTemplate
- `src/lib/whatsapp/encryption.ts` — AES-256-GCM token encryption
- `src/lib/whatsapp/auth.ts` — credential resolution with decryption
- `src/lib/whatsapp/template-components.ts` — WhatsApp template component builder
- `src/lib/whatsapp/template-validators.ts` — validation logic
- `src/lib/whatsapp/template-send-builder.ts` — send payload builder
- `src/components/settings/WhatsAppConnectPanel.tsx` — full UI (27KB)

---

### 4.16 Billing & Checkout (`src/app/dashboard/billing/page.tsx` + `src/app/checkout/page.tsx`)

**Status: ❌ MOCKED / BROKEN — Not Production Ready**

**Critical issues:**

1. **Checkout page hits hardcoded `localhost`:**
   ```typescript
   // src/app/checkout/page.tsx line ~70
   const res = await fetch('http://localhost:8000/executor/billing/checkout/', { ... })
   ```
   This will fail completely in production. Must be `process.env.NEXT_PUBLIC_ENGINE_URL + '/executor/billing/checkout/'`

2. **Razorpay key is a placeholder:**
   ```typescript
   // src/app/checkout/page.tsx
   key: 'rzp_test_mock_key_for_now',
   ```
   Must be replaced with `process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID` (test key: `rzp_test_XXXXXXXX`)

3. **The engine's billing backend is mocked** (see Section 3 — `billing_views.py`)

4. **Coupon code is hardcoded:**
   ```typescript
   // src/app/checkout/page.tsx
   if (couponCode === 'FOUNDER20') { setDiscountPercent(20) }
   ```
   Must validate against backend `Coupon` table

5. **Plan prices are hardcoded in the frontend** — should come from an API or Razorpay Plans

6. **`src/components/billing/FeatureMatrix.tsx`** (7KB) and **`src/components/billing/HardPaywallOverlay.tsx`** (4KB) — UI components exist but the paywall is never enforced — no middleware or API route checks plan status

7. **`src/components/billing/PricingCard.tsx`** (2KB) — pricing card UI only

8. **`/api/billing/credits/route.ts`** — reads from `credit_wallets` and `credit_ledger` tables in Supabase. These tables may not exist in the schema — they're not in the main migration files visible in the zip.

**What's needed for production billing:**
- Create Razorpay account, get test API key
- Add real `razorpay` Python package to engine `requirements.txt`
- Add `WorkspaceSubscription`, `Coupon`, `AICreditLedger`, `AICreditTransaction` Django models with migration
- Add `credit_wallets` and `credit_ledger` tables to Supabase migrations
- Replace hardcoded `localhost:8000` with env var
- Replace `rzp_test_mock_key_for_now` with real test key
- Add `RAZORPAY_WEBHOOK_SECRET` env var to engine
- Implement HMAC signature verification in webhook handler
- Add paywall enforcement in middleware or API routes

---

### 4.17 Onboarding (`src/app/onboarding/page.tsx`)

**Status: ✅ Connected & Real**

- Multi-step onboarding — 22KB
- Creates workspace, sends WhatsApp setup prompts
- Real Supabase writes

---

### 4.18 Widget (`src/app/widget/chat/page.tsx`)

**Status: ✅ Connected & Real**

- Embeddable chat widget
- `/api/widget/embed.js/route.ts` — serves the JavaScript snippet for embedding
- `/api/widget/config/route.ts` — returns widget config
- `/api/widget/chat/route.ts` — handles widget messages

---

## 5. CRITICAL ISSUES & SECURITY EXPOSURES

### ⛔ Secrets Exposed in .env (committed to zip)

The following **live credentials** are in the committed `.env` files and must be rotated immediately:

| Secret | Value (first chars) | Action |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGci...` | ⚠️ Rotate in Supabase dashboard |
| `META_ACCESS_TOKEN` | `EAAkz69v...` | ⚠️ Rotate in Meta Business |
| `GEMINI_API_KEY` | `AIzaSyBx...` | ⚠️ Rotate in Google Cloud |
| `LIVEKIT_API_SECRET` | `ayM5j8kT...` | ⚠️ Rotate in LiveKit |
| `SARVAM_API_KEY` | `sk_rr0ke6...` | ⚠️ Rotate |
| `DEEPGRAM` | `2aa926f4...` | ⚠️ Rotate |
| `TINYFISH_API_KEY` | `sk-tinyfish...` | ⚠️ Rotate |
| `SUPABASE_S3_SECRET` | `11f0d836...` | ⚠️ Rotate |
| `ENCRYPTION_KEY` | `30c700bb...` | ⚠️ Generate new 32-byte hex |
| `TRIGGER_SECRET_KEY` | `tr_prod_Bzi...` | ⚠️ Rotate in Trigger.dev |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full private key | ⚠️ Rotate GCP SA |
| `DB_PASSWORD` | `Sumit700@32` | ⚠️ Change Supabase DB password |
| `FLOWRA_SECRET / DOGRAH_SECRET` | `sumit` | ⚠️ Change to random 32+ char string |
| `ENGINE_SECRET_KEY` | `sumit` | ⚠️ Change |
| `OSS_JWT_SECRET` | `8e18e0fa...` | ⚠️ Already random, keep private |

---

## 6. DEPLOYMENT CONFIGURATION REVIEW

### Flowra Frontend → Vercel Free Plan

**File:** `vercel.json` (root of flowra_frontend.zip)

```json
{
  "framework": "nextjs",
  "regions": ["bom1"],
  "functions": {
    "src/app/api/**": { "maxDuration": 60 }
  }
}
```

**Issues:**
- `maxDuration: 60` seconds — Vercel free plan allows max 10 seconds for hobby, 60 seconds for Pro. **Verify your plan allows 60s.** If you're on free/hobby, API routes will timeout at 10s.
- WhatsApp webhook processing, workflow execution, and knowledge upload may exceed 10s. These should be offloaded to Trigger.dev tasks.
- CORS headers in `vercel.json` are wide open (`*`) — acceptable for API routes that verify auth themselves, but review for production.

**Missing env vars that must be added to Vercel:**
- `NEXT_PUBLIC_ENGINE_URL` — URL of the deployed Flowra Engine on Google Cloud
- `NEXT_PUBLIC_RAZORPAY_KEY_ID` — Razorpay test key ID
- All existing vars from `.env` (already have values, just need to be added to Vercel dashboard)

### Flowra Engine → Google Cloud Free ($300 credits)

**Recommended:** Cloud Run (serverless containers) — works well with Celery via Cloud Tasks or Cloud Scheduler.

**Issues:**
- `ALLOWED_HOSTS = ['*']` — must be set to your Cloud Run service URL
- `DEBUG = True` — must be `False` in production
- `SECRET_KEY = 'sumit'` — must be changed
- The engine has no Dockerfile currently — needs one for Cloud Run deployment
- Celery Beat (60s poll) works fine on a single Cloud Run instance but won't work if Cloud Run scales to zero. Consider using Google Cloud Scheduler to trigger the polling task via HTTP instead of Celery Beat for the free tier.
- `requirements.txt` only has: `Django`, `djangorestframework`, `psycopg2-binary`, `celery`, `redis`, `requests`, `python-dotenv`, `pandas`, `openpyxl`, `cryptography`. Missing: `razorpay`, `gunicorn` (for production WSGI), `whitenoise` (static files).

### Dograh → Google Cloud Free ($300 credits)

**Recommended:** Cloud Run with minimum 1 instance (voice calls need always-on WebSocket)

**Issues:**
- Voice calls require persistent WebSocket connections — Cloud Run's request timeout (60min max) could cut long calls. Set `--timeout=3600` in Cloud Run.
- `PUBLIC_BASE_URL` in `.env` is the ngrok URL — must be updated to Cloud Run service URL
- `FLOWRA_API_URL` points to `https://flowora-six.vercel.app` (typo? should be `flowra`) — verify the Vercel deployment URL
- `FLOWRA_WEBHOOK_URL` and `FLOWRA_WEBHOOK_SECRET` — confirm these are set correctly when Dograh calls back to Flowra
- S3 (Cloudflare R2 via T3) is configured for audio recording storage — credentials look real ✅
- Railway PostgreSQL is configured in Dograh's `.env` (`DATABASE_URL=postgresql+asyncpg://postgres:PKrLs...@postgres.railway.internal`) — this is a **Railway internal URL** that won't work from Google Cloud. You need a public PostgreSQL URL or migrate to Google Cloud SQL / Supabase for Dograh's own DB.

---

## 7. WHAT NEEDS TO BE FIXED BEFORE DEPLOY

### Priority 1 — Blockers (will not work at all)

1. **Checkout hardcoded to `localhost:8000`** — `src/app/checkout/page.tsx` line ~70
2. **Razorpay key is placeholder** — `rzp_test_mock_key_for_now`
3. **Engine billing is fully mocked** — `executor/billing_views.py`
4. **Dograh's Railway DB won't work from Google Cloud** — needs accessible PostgreSQL
5. **`FLOWRA_SECRET="sumit"`** — insecure cross-service auth used in production
6. **`DEBUG=True` in engine** — security risk
7. **`ALLOWED_HOSTS=['*']` in engine** — must restrict to actual domain
8. **Integrations page is a stub** — `src/app/dashboard/integrations/page.tsx`
9. **Gemini Live model string** — `gemini-2.0-flash-exp` may be deprecated; verify current Preview API model name

### Priority 2 — Functional Issues (will work but incorrectly)

10. **Voice Agent UI shows 30 Gemini voices** but only 5 are supported — confusing UX
11. **LiveKit fields in Voice settings** are dead UI noise now that Vobiz is telephony
12. **Toast copy references "LiveKit" and "VoiceLink"** — stale, should say "Vobiz/Dograh"
13. **QStash import in `src/lib/qstash.ts`** — may conflict with Trigger.dev if both are active
14. **`credit_wallets`/`credit_ledger` tables** — may not exist in Supabase — add migration
15. **Coupon hardcoded** — `if (couponCode === 'FOUNDER20')` in checkout page

### Priority 3 — Security & Quality

16. **All live secrets committed to `.env` files** — rotate everything
17. **`ENCRYPTION_KEY` is committed** — this key encrypts WhatsApp tokens in the DB
18. **`GOOGLE_SERVICE_ACCOUNT_JSON` full private key committed** — rotate GCP SA
19. **`DEBUG=True` defaults** in engine settings
20. **Engine has no Dockerfile** — needed for Cloud Run deployment

### Vobiz Migration Checklist (no code changes needed)

- [ ] Get Vobiz `auth_id` and `auth_token` from Vobiz dashboard
- [ ] In Dograh UI → Settings → Telephony → Add Vobiz config
- [ ] Set Vobiz as default org telephony provider in Dograh
- [ ] Update `PUBLIC_BASE_URL` in Dograh `.env` to Google Cloud URL (not ngrok)
- [ ] Remove `VOICELINK_SIP_TECH_PREFIX` from Flowra Frontend `.env` (no longer needed)
- [ ] Optionally remove `LIVEKIT_*` vars from Flowra Frontend `.env` if not used for anything else
- [ ] In Flowra Frontend Settings → Voice & Calling → set Dograh Phone Number to your Vobiz DID

---

## 8. FULL FILE INVENTORY WITH STATUS

### Flowra Frontend (`flowra_frontend.zip`)

#### API Routes (`src/app/api/`)

| File | Status | Notes |
|---|---|---|
| `admin/run-migration/route.ts` | ⚠️ Dev only | Admin route to run DB migrations — should be removed or secured in prod |
| `analytics/route.ts` | ✅ Real | Supabase analytics aggregation |
| `billing/credits/route.ts` | ⚠️ Needs tables | Reads credit_wallets/credit_ledger — tables may not exist |
| `campaigns/route.ts` | ✅ Real | WhatsApp campaign CRUD + send |
| `campaigns/process-queue/route.ts` | ⚠️ Review | Queue drain — confirm Trigger.dev or Vercel cron handles this |
| `campaigns/schedule/route.ts` | ✅ Real | Schedule campaigns |
| `campaigns/[id]/route.ts` | ✅ Real | Campaign CRUD by ID |
| `chatbot/faqs/route.ts` | ✅ Real | FAQ management |
| `chatbot/route.ts` | ✅ Real | Chatbot settings CRUD |
| `chatbot/test/route.ts` | ✅ Real | Test chat against Gemini |
| `chats/route.ts` | ✅ Real | Chat messages |
| `contacts/route.ts` | ✅ Real | Contact CRUD + import |
| `inbox/assign/route.ts` | ✅ Real | Thread assignment |
| `inbox/routing/helper.ts` | ✅ Real | Routing rule helpers |
| `inbox/routing/route.ts` | ✅ Real | Inbox routing rules |
| `inbox/threads/route.ts` | ✅ Real | Thread list |
| `inbox/threads/[id]/messages/route.ts` | ✅ Real | Messages per thread |
| `inbox/threads/[id]/route.ts` | ✅ Real | Thread detail |
| `inbox/upload-media/route.ts` | ✅ Real | Media upload to Supabase Storage |
| `invite/[token]/accept/route.ts` | ✅ Real | Accept workspace invite |
| `invite/[token]/peek/route.ts` | ✅ Real | Preview invite |
| `jobs/campaign-execute/route.ts` | ✅ Real | Trigger.dev campaign job handler |
| `jobs/workflow-step/route.ts` | ✅ Real | Trigger.dev workflow step handler |
| `knowledge/documents/route.ts` | ✅ Real | Knowledge source management |
| `knowledge/query/route.ts` | ✅ Real | RAG query |
| `knowledge/upload/route.ts` | ✅ Real | File upload to knowledge-files bucket |
| `lead-capture/route.ts` | ✅ Real | Lead capture settings |
| `leads/route.ts` | ✅ Real | Leads CRUD (12KB) |
| `messages/route.ts` | ✅ Real | Message send |
| `settings/keys/route.ts` | ✅ Real | Encrypted credential storage |
| `settings/route.ts` | ✅ Real | Workspace settings |
| `settings/test-smtp/route.ts` | ✅ Real | SMTP test |
| `team/route.ts` | ✅ Real | Team management |
| `templates/route.ts` | ✅ Real | Message template CRUD |
| `test-env/route.ts` | ⚠️ Dev only | Returns env var test — remove in prod |
| `tickets/route.ts` | ✅ Real | Ticket CRUD |
| `tickets/[id]/escalate/route.ts` | ✅ Real | Ticket escalation |
| `tickets/[id]/notes/route.ts` | ✅ Real | Internal notes |
| `webhooks/whatsapp/route.ts` | ✅ Real | WhatsApp inbound webhook (14KB) |
| `whatsapp/config/route.ts` | ✅ Real | WhatsApp channel config (10KB) |
| `whatsapp/config/verify-registration/route.ts` | ✅ Real | Phone registration verification |
| `whatsapp/templates/submit/route.ts` | ✅ Real | Template submission to Meta |
| `whatsapp/templates/sync/route.ts` | ✅ Real | Template sync from Meta |
| `whatsapp/templates/[id]/route.ts` | ✅ Real | Template management |
| `widget/chat/route.ts` | ✅ Real | Widget chat handler |
| `widget/config/route.ts` | ✅ Real | Widget config |
| `widget/embed.js/route.ts` | ✅ Real | JavaScript embed snippet |
| `workflows/fetch-sheet-headers/route.ts` | ✅ Real | Google Sheets header fetch |
| `workflows/route.ts` | ✅ Real | Workflow CRUD |
| `workflows/runs/route.ts` | ✅ Real | Workflow run history |
| `workflows/trigger/route.ts` | ✅ Real | Trigger workflow execution |
| `workspace/api-keys/route.ts` | ✅ Real | API key management |
| `workspace/api-keys/[id]/route.ts` | ✅ Real | API key delete |
| `workspace/invitations/route.ts` | ✅ Real | Invitation management |
| `workspace/invitations/[id]/route.ts` | ✅ Real | Invitation CRUD |
| `workspace/members/route.ts` | ✅ Real | Member management |
| `workspace/members/[id]/route.ts` | ✅ Real | Member detail |
| `workspace/presence/route.ts` | ✅ Real | Online presence heartbeat |
| `workspaces/route.ts` | ✅ Real | Workspace CRUD |

#### Page Files (`src/app/`)

| File | Status | Notes |
|---|---|---|
| `auth/callback/route.ts` | ✅ Real | Supabase OAuth callback |
| `auth/login/page.tsx` | ✅ Real | Login page (10KB) |
| `auth/signup/page.tsx` | ✅ Real | Signup with workspace creation (19KB) |
| `checkout/page.tsx` | ❌ Broken | Hardcoded localhost:8000, mock Razorpay key |
| `dashboard/analytics/page.tsx` | ✅ Real | Analytics dashboard |
| `dashboard/billing/page.tsx` | ⚠️ UI only | Routes to checkout — checkout is broken |
| `dashboard/broadcasts/page.tsx` | ✅ Real | Broadcast management |
| `dashboard/campaigns/page.tsx` | ✅ Real | Campaign management (28KB) |
| `dashboard/chatbot/page.tsx` | ✅ Real | Chatbot config (83KB) |
| `dashboard/contacts/page.tsx` | ✅ Real | Contact management (52KB) |
| `dashboard/inbox/page.tsx` | ✅ Real | Shared inbox (100KB — very large) |
| `dashboard/integrations/page.tsx` | ❌ Stub | "Coming soon" — 171 bytes |
| `dashboard/knowledge/page.tsx` | ✅ Real | Knowledge base (38KB) |
| `dashboard/lead-capture/page.tsx` | ✅ Real | Lead capture (thin wrapper) |
| `dashboard/leads/page.tsx` | ✅ Real | Leads CRM Kanban (43KB) |
| `dashboard/page.tsx` | ✅ Real | Main dashboard |
| `dashboard/settings/page.tsx` | ⚠️ Mostly real | 63KB — some dead fields |
| `dashboard/team/page.tsx` | ✅ Real | Team management (31KB) |
| `dashboard/tickets/page.tsx` | ✅ Real | Ticket management (18KB) |
| `dashboard/tickets/[id]/page.tsx` | ✅ Real | Ticket detail |
| `dashboard/voice-agent/calls/page.tsx` | ✅ Real | Call history (19KB) |
| `dashboard/voice-agent/page.tsx` | ⚠️ Partial | Needs Vobiz UI updates, Gemini voice list |
| `dashboard/voice-agent/voices/page.tsx` | ⚠️ Cosmetic | Shows all voices including unsupported (15KB) |
| `dashboard/workflows/builder/page.tsx` | ✅ Real | Workflow builder (90KB) |
| `dashboard/workflows/page.tsx` | ✅ Real | Workflow list (14KB) |
| `invite/[token]/page.tsx` | ✅ Real | Invite acceptance page (8KB) |
| `onboarding/page.tsx` | ✅ Real | Onboarding flow (22KB) |
| `widget/chat/page.tsx` | ✅ Real | Embedded chat widget (9KB) |

#### Library & Service Files (`src/lib/`, `src/services/`)

| File | Status | Notes |
|---|---|---|
| `lib/api/mock-db.ts` | ⚠️ Legacy | Hardcoded mock data — confirm nothing production imports this |
| `lib/campaign/executor.ts` | ✅ Real | Campaign executor |
| `lib/crypto.ts` | ✅ Real | AES-256-GCM encryption for secrets |
| `lib/currency.ts` | ✅ Real | Multi-currency formatting |
| `lib/livekit.ts` | ⚠️ Stale | LiveKit SDK — mostly unused with Vobiz |
| `lib/livekit/normalize-url.ts` | ⚠️ Stale | URL normalizer for LiveKit |
| `lib/presence.ts` | ✅ Real | Presence utilities |
| `lib/qstash.ts` | ⚠️ Audit | QStash — may conflict with Trigger.dev |
| `lib/razorpay.ts` | ⚠️ Incomplete | Only loads the SDK script, no server-side logic |
| `lib/redis.ts` | ✅ Real | Upstash Redis client |
| `lib/supabase/client.ts` | ✅ Real | Browser Supabase client |
| `lib/supabase/server.ts` | ✅ Real | Server Supabase client with SSR |
| `lib/tenant.ts` | ✅ Real | Multi-tenant workspace resolution |
| `lib/tinyfish.ts` | ✅ Real | URL scraping for knowledge base |
| `lib/utils.ts` | ✅ Real | Utility functions |
| `lib/voices.ts` | ✅ Real | Voice definitions (17KB) |
| `lib/whatsapp/auth.ts` | ✅ Real | WhatsApp credential resolution |
| `lib/whatsapp/encryption.ts` | ✅ Real | Token encryption/decryption |
| `lib/whatsapp/meta-api.ts` | ✅ Real | Meta Graph API calls (23KB) |
| `lib/whatsapp/template-components.ts` | ✅ Real | Template builder |
| `lib/whatsapp/template-header-handle.ts` | ✅ Real | Template header handling |
| `lib/whatsapp/template-send-builder.ts` | ✅ Real | Send payload builder |
| `lib/whatsapp/template-status-normalize.ts` | ✅ Real | Template status normalization |
| `lib/whatsapp/template-validators.ts` | ✅ Real | Template validation (9KB) |
| `lib/whatsapp-variables.ts` | ✅ Real | Variable interpolation |
| `lib/workflow/executor.ts` | ✅ Real | Sync workflow executor (17KB) |
| `lib/workflow/reminders.ts` | ✅ Real | Reminder/delay scheduling |
| `lib/workflow/trigger.ts` | ✅ Real | Trigger condition evaluation (10KB) |
| `lib/workflow-templates.ts` | ✅ Real | 18 workflow templates |
| `services/ai.ts` | ✅ Real | Gemini chatbot AI service (12KB) |
| `services/audit.ts` | ✅ Real | Audit logging |
| `services/credits.ts` | ⚠️ Partial | Credit deduction service — needs billing tables |
| `services/gemini-cache.ts` | ✅ Real | Gemini prompt context caching |
| `services/lead-capture.ts` | ✅ Real | Lead capture service (26KB) |
| `services/mailer.ts` | ✅ Real | SMTP email service (9KB) |
| `services/meta.ts` | ✅ Real | Meta WhatsApp API wrapper (6KB) |
| `services/notifications.ts` | ✅ Real | In-app notifications |
| `services/rag.ts` | ✅ Real | Vector search / RAG (6KB) |
| `services/scheduler.ts` | ✅ Real | Job scheduling |
| `services/tickets.ts` | ✅ Real | Ticket service logic (12KB) |
| `services/voice.ts` | ✅ Real | Voice call initiation → Dograh (6KB) |
| `trigger/knowledge.ts` | ✅ Real | Trigger.dev knowledge processing task (14KB) |

#### Component Files (`src/components/`)

| File | Status | Notes |
|---|---|---|
| `billing/FeatureMatrix.tsx` | ⚠️ UI only | Pricing table — no enforcement |
| `billing/HardPaywallOverlay.tsx` | ⚠️ UI only | Paywall overlay — not wired to plan checks |
| `billing/PricingCard.tsx` | ⚠️ UI only | Pricing card component |
| `campaign/campaign-sender.tsx` | ✅ Real | Full campaign send UI (19KB) |
| `chat/inbox-client.tsx` | ✅ Real | Inbox client component (12KB) |
| `contacts/contact-sidebar.tsx` | ✅ Real | Contact sidebar (11KB) |
| `contacts/contacts-table.tsx` | ✅ Real | Contacts table (6KB) |
| `dashboard/DashboardShell.tsx` | ✅ Real | Dashboard shell wrapper |
| `lead-capture/lead-capture-client.tsx` | ✅ Real | Lead capture UI (90KB) |
| `organisms/KanbanBoard.tsx` | ✅ Real | Leads kanban (19KB) |
| `organisms/Sidebar.tsx` | ✅ Real | Main sidebar (14KB) |
| `organisms/Topbar.tsx` | ✅ Real | Top navigation (9KB) |
| `organisms/WorkflowCanvas.tsx` | ✅ Real | Workflow canvas (18KB) |
| `presence/PresenceDot.tsx` | ✅ Real | Online indicator |
| `presence/PresenceHeartbeat.tsx` | ✅ Real | Presence heartbeat |
| `settings/DealsSettingsPanel.tsx` | ✅ Real | Deal stage settings (4KB) |
| `settings/TagsAndFieldsPanel.tsx` | ✅ Real | Tags & custom fields (16KB) |
| `settings/TemplateManagerPanel.tsx` | ✅ Real | Template manager (38KB) |
| `settings/WhatsAppConnectPanel.tsx` | ✅ Real | WhatsApp connection (27KB) |
| `tickets/ticket-detail-client.tsx` | ✅ Real | Ticket detail (34KB) |

#### Config Files

| File | Status | Notes |
|---|---|---|
| `.env` | ❌ INSECURE | Live credentials committed — rotate all |
| `.env.example` | ✅ Good | Well documented |
| `next.config.ts` | ✅ OK | Standard Next.js config |
| `vercel.json` | ⚠️ Check limits | 60s max duration — verify Vercel plan |
| `trigger.config.ts` | ✅ Real | Trigger.dev project configured |
| `tsconfig.json` | ✅ Real | Standard TS config |
| `tailwind.config.js` | ✅ Real | Tailwind with custom colors |
| `middleware.ts` | ✅ Real | Supabase session middleware |
| `src/instrumentation.ts` | ✅ Real | Next.js instrumentation hook |

#### Database Files (`database/`, `supabase/migrations/`)

| File | Status | Notes |
|---|---|---|
| `supabase/migrations/001_tenancy_foundation.sql` | ✅ Core | Main schema — workspaces, contacts, messages, workflows |
| `supabase/migrations/002_whatsapp_calls.sql` | ✅ Core | WhatsApp + voice calls tables |
| `supabase/migrations/003_workspace_invitations.sql` | ✅ Core | Invitation system |
| `supabase/migrations/004_api_keys.sql` | ✅ Core | API key management |
| `supabase/migrations/005_member_presence.sql` | ✅ Core | Presence tracking |
| `supabase/migrations/006_notifications_workspace.sql` | ✅ Core | Notifications |
| `supabase/migrations/007_tags.sql` | ✅ Core | Tags system |
| `supabase/migrations/008_channel_connections_registration_fields.sql` | ✅ Core | Channel config |
| `supabase/migrations/009_message_templates.sql` | ✅ Core | Template storage |
| `supabase/migrations/010_custom_field_schemas.sql` | ✅ Core | Custom fields |
| `supabase/migrations/011_workspaces_default_currency.sql` | ✅ Core | Currency support |
| `supabase/migrations/012_fix_custom_field_schemas_columns.sql` | ✅ Fix | Schema fix |
| `supabase/migrations/013_workspace_members_extended.sql` | ✅ Core | Extended member data |
| `supabase/migrations/014_fix_user_trigger.sql` | ✅ Fix | Trigger fix |
| `supabase/migrations/015_add_lead_custom_columns_and_header_media.sql` | ✅ Core | Lead columns |
| `supabase/migrations/016_fix_message_templates_status_constraint.sql` | ✅ Fix | Status fix |
| `supabase/migrations/017_add_rejection_reason.sql` | ✅ Fix | Rejection tracking |
| `supabase/migrations/018_relax_message_templates_constraints.sql` | ✅ Fix | Constraint fix |
| `supabase/migrations/019_fix_presence_offline.sql` | ✅ Fix | Presence fix |
| `database/migration-knowledge-base.sql` | ✅ Core | Knowledge base + pgvector |
| `database/migration-voice-settings.sql` | ✅ Core | Voice agent settings |
| `database/migrations/001_multi_tenant.sql` | ✅ Core | Multi-tenancy |
| `database/migrations/002_tickets.sql` | ✅ Core | Ticket system |
| ❌ MISSING | `credit_wallets` table | Not in any migration — needed for billing |
| ❌ MISSING | `credit_ledger` table | Not in any migration — needed for billing |

---

### Flowra Engine (`flowra_engine.zip`)

| File | Status | Notes |
|---|---|---|
| `executor/engine.py` | ✅ Real | Core workflow engine (35KB) |
| `executor/models.py` | ⚠️ Partial | Real models, but billing models not in migration |
| `executor/billing_views.py` | ❌ Mocked | Razorpay is mocked |
| `executor/tasks.py` | ✅ Real | Celery task: polls Google Sheets every 60s |
| `executor/views.py` | ✅ Real | Workflow execution endpoint |
| `executor/urls.py` | ✅ Real | URL routing |
| `executor/admin.py` | ✅ Real | Django admin |
| `executor/migrations/0001_initial.py` | ⚠️ Incomplete | Missing billing models |
| `flowra_engine/settings.py` | ❌ Insecure | DEBUG=True, ALLOWED_HOSTS=['*'] |
| `flowra_engine/celery.py` | ✅ Real | Celery configuration |
| `flowra_engine/urls.py` | ✅ Real | URL routing |
| `.env` | ❌ Insecure | `SECRET_KEY=sumit`, `DOGRAH_SECRET=change-me` |
| `requirements.txt` | ⚠️ Incomplete | Missing `razorpay`, `gunicorn`, `whitenoise` |
| ❌ MISSING | `Dockerfile` | Needed for Cloud Run deployment |
| ❌ MISSING | `.gcloudignore` | Needed for Cloud Run deployment |

---

### Dograh OSS (`dograh.zip`)

| File/Path | Status | Notes |
|---|---|---|
| `api/services/telephony/providers/vobiz/__init__.py` | ✅ Complete | Vobiz provider spec, auto-creates Application |
| `api/services/telephony/providers/vobiz/provider.py` | ✅ Complete | Full outbound call, inbound normalization |
| `api/services/telephony/providers/vobiz/transport.py` | ✅ Complete | FastAPI WebSocket transport, MULAW 8kHz |
| `api/services/telephony/providers/vobiz/serializers.py` | ✅ Complete | Frame serializer with HMAC auth |
| `api/services/telephony/providers/vobiz/config.py` | ✅ Complete | Pydantic config schemas |
| `api/services/telephony/providers/vobiz/routes.py` | ✅ Complete | Webhook routes |
| `api/services/telephony/providers/voicelink/` | ✅ Kept | Old provider — leave in place, just don't set as default |
| `api/services/pipecat/service_factory.py` | ✅ Real | Pipecat pipeline factory with Gemini Live |
| `api/services/configuration/registry.py` | ✅ Real | `GOOGLE_REALTIME` registered |
| `api/db/telephony_configuration_client.py` | ✅ Real | Telephony config DB operations |
| `api/db/telephony_phone_number_client.py` | ✅ Real | Phone number management |
| `api/routes/telephony.py` | ✅ Real | Telephony routes (initiate, inbound, webhook) |
| `api/routes/organization.py` | ✅ Real | Org settings with telephony UI metadata |
| `api/alembic/versions/a188ff90e76f_add_vobiz_mode_for_workflow.py` | ✅ Applied | Vobiz enum value added |
| `api/alembic/versions/a2355fc6bdc1_add_multi_telephony_config_tables.py` | ✅ Applied | Multi-provider config tables |
| `.env` | ⚠️ Config needed | Railway DB URL won't work from Google Cloud |
| `docker-compose.yaml` | ✅ Reference | Use for local dev, adapt for Cloud Run |
| `api/Dockerfile` | ✅ Exists | Ready for container deployment |
| `api/native/rnnoise/librnnoise.so.0.4.1` | ✅ Real | Background noise cancellation |

---

## Summary Scorecard

| Feature | Flowra Frontend | Flowra Engine | Dograh | Overall |
|---|---|---|---|---|
| WhatsApp Messaging | ✅ Real | ✅ Real | N/A | ✅ Ready |
| Shared Inbox | ✅ Real | N/A | N/A | ✅ Ready |
| Contacts CRM | ✅ Real | N/A | N/A | ✅ Ready |
| Leads Kanban | ✅ Real | N/A | N/A | ✅ Ready |
| Workflows Builder | ✅ Real | ✅ Real | N/A | ✅ Ready |
| Campaigns | ✅ Real | ✅ Real | N/A | ✅ Ready |
| Lead Capture | ✅ Real | ✅ Real | N/A | ✅ Ready |
| AI Chatbot | ✅ Real | N/A | N/A | ✅ Ready |
| Knowledge Base | ✅ Real | N/A | N/A | ✅ Ready |
| Analytics | ✅ Real | N/A | N/A | ✅ Ready |
| Team & Presence | ✅ Real | N/A | N/A | ✅ Ready |
| Voice (Gemini Live) | ✅ Real | N/A | ✅ Real | ⚠️ Needs Vobiz config |
| Voice (Sarvam/Groq) | ✅ Real | N/A | ✅ Real | ⚠️ Needs Vobiz config |
| Telephony (Vobiz) | N/A | N/A | ✅ Code done | ⚠️ Needs credential config |
| Billing / Razorpay | ❌ Broken UI | ❌ Mocked | N/A | ❌ Not ready |
| Trigger.dev | ✅ Configured | N/A | N/A | ✅ Ready |
| Tickets | ✅ Real | N/A | N/A | ✅ Ready |
| Broadcasts | ✅ Real | N/A | N/A | ✅ Ready |
| Integrations Page | ❌ Stub | N/A | N/A | ❌ Not ready |
| Security | ❌ Secrets exposed | ❌ DEBUG=True | ⚠️ Railway DB issue | ❌ Fix before prod |

---

*Report generated by analysis of dograh.zip (3331 files), flowra_frontend.zip (538 files), flowra_engine.zip (54 files). No code changes were made — analysis only.*
