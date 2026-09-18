# 🚀 Flowra Engine (Django Background Worker & Workflow Service)

`flowra-engine` is a standalone Django 5 REST and Celery microservice designed to run alongside the Flowra Next.js frontend. It offloads all CPU-intensive and time-sensitive background tasks—specifically **Workflow Execution** and **Google Sheets Lead Capture Polling**—away from Vercel's serverless containers.

---

## 🏛️ Why This Architecture?
1. **No Vercel Timeouts**: Vercel free/serverless containers terminate background timers and long-polling HTTP connections after 10 seconds. Django + Celery runs continuously without time limits.
2. **Shared Supabase Database**: This Django engine uses unmanaged ORM models (`managed = False`) to directly query and modify your existing Supabase PostgreSQL tables (`workflows`, `workflow_runs`, `contacts`, `lead_capture_settings`, etc.) without altering their schema.
3. **No Cron Jobs in Next.js**: Flowra Next.js is strictly a UI, API, and live voice control plane.

---

## 🔌 API Endpoints

### 1. Trigger Workflow Execution
Triggered by Flowra Next.js when testing workflows or when webhooks arrive from external sources.
- **URL**: `POST /api/execute/workflow/`
- **Headers**:
  ```http
  Authorization: Bearer <ENGINE_SECRET_KEY>
  Content-Type: application/json
  ```
- **Payload**:
  ```json
  {
    "workflowId": "95171a17-ed30-446d-aee5-9317c2b2b7e4",
    "workspaceId": "your-workspace-uuid",
    "triggerData": {
      "phone": "9999988888",
      "name": "VIP Customer",
      "email": "vip@customer.com",
      "status": "VIP"
    },
    "async": true
  }
  ```
- **Response** (`202 ACCEPTED` if async, `200 OK` if synchronous):
  ```json
  {
    "status": "queued",
    "task_id": "c80d957c-e330-4574-b51e-4713be2b9353",
    "workflow_id": "95171a17-ed30-446d-aee5-9317c2b2b7e4"
  }
  ```

### 2. Poll Lead Capture Campaigns
Checks all active Google Sheets campaigns, imports new leads into `lead_capture_leads`, and triggers associated workflows.
- **URL**: `POST /api/execute/poll-sheets/`
- **Headers**:
  ```http
  Authorization: Bearer <ENGINE_SECRET_KEY>
  Content-Type: application/json
  ```
- **Payload**:
  ```json
  {
    "async": true
  }
  ```

---

## 🛠️ Local Development & Running

### 1. Configure Environment
Copy `.env.example` to `.env` and fill in your Supabase PostgreSQL credentials:
```bash
cp .env.example .env
```

### 2. Run Django API Server
```bash
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8001
```

### 3. Run Celery Worker (in a separate terminal)
Requires Redis running locally or via cloud (Upstash/Railway Redis):
```bash
.\venv\Scripts\celery.exe -A flowra_engine worker -l info -P eventlet
```

---

## 📦 Deployment (Railway / Render / Fly.io)

1. **Web Process**:
   ```bash
   gunicorn flowra_engine.wsgi:application --bind 0.0.0.0:$PORT
   ```
2. **Worker Process**:
   ```bash
   celery -A flowra_engine worker --loglevel=info
   ```
3. **Beat Process (Optional for automatic polling every 5 minutes)**:
   ```bash
   celery -A flowra_engine beat --loglevel=info
   ```
