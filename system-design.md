# System Design — Recipe Video App

**Date:** 2026-05-24  
**Scope:** v1 — public web + Android app that ingests social media cooking videos, transcribes them, and extracts structured recipes using AI.

---

## 1. Requirements

### Functional (v1)
- User submits a video URL from TikTok, YouTube, Instagram, or Facebook
- System downloads the video and fetches the post description/caption
- System transcribes the video audio (speech-to-text)
- AI model compares transcription + description and outputs a structured recipe (title, ingredients, steps, notes)
- Recipe is saved to the user's personal recipe book
- User can browse their saved recipes (web + Android)

### Non-Functional
- **Async processing** — video ingestion + transcription can take 30–120 seconds; must not block the HTTP response
- **Scale** — public app; design for 1,000 concurrent users, 10,000 daily video submissions
- **Storage** — average video file 50–200 MB; recipe text is tiny (~5 KB)
- **Availability** — 99.5% uptime acceptable for v1
- **Cost** — keep AI/transcription API costs per recipe under ~$0.05

### Constraints (v1)
- Video sources: TikTok, YouTube, Instagram, Facebook public posts only
- Private/paywalled content is out of scope
- Recipe editing (manual) is post-v1

---

## 2. High-Level Architecture

The system is a **five-layer pipeline**:

```
Clients (Web + Android)
    ↓ HTTPS
REST API Gateway  (auth, routing, rate limiting)
    ↓ async job
Job Queue  (Redis / BullMQ)
    ↓ workers
Processing Pipeline:
  [1. Video Ingestion] → [2. Transcription] → [3. Recipe AI]
    ↓                                              ↓
S3 Storage (video files)             PostgreSQL (recipes, users, jobs)
```

The key design decision is **async job processing via a queue**. The API responds immediately with a job ID; the client polls for status while the pipeline runs in the background.

---

## 3. Component Design

### 3.1 Client Apps

**Web App (React + Vite)**
- Single-page app hosted on Vercel or Cloudflare Pages
- Key screens: Submit URL → Processing status → Recipe book → Recipe detail
- Polling or WebSocket for job status updates

**Android App (React Native)**
- Shares ~80% of code with the web app via a monorepo
- Android deep-link integration: user can share a video from TikTok/Instagram directly to the app via the system share sheet

### 3.2 REST API Gateway (Node.js + Express or Fastify)

Responsibilities:
- JWT authentication (sign-up/log-in via email or Google OAuth)
- Request validation and rate limiting (e.g. 20 submissions/hour/user)
- Enqueues jobs to Redis
- Exposes polling endpoint for job status

Key endpoints:
```
POST   /auth/register
POST   /auth/login
POST   /jobs              → submit video URL, returns { jobId }
GET    /jobs/:id          → returns job status + recipeId when done
GET    /recipes           → list user's recipes (paginated)
GET    /recipes/:id       → full recipe detail
DELETE /recipes/:id
```

### 3.3 Job Queue (Redis + BullMQ)

Each submitted URL becomes a **job** pushed to the `video-pipeline` queue. BullMQ handles:
- Retry logic (3 retries with exponential backoff)
- Job priority (could be extended later for premium users)
- Dead-letter queue for failed jobs
- Job progress events (for polling endpoint)

### 3.4 Processing Pipeline (Workers)

#### Worker 1 — Video Ingestion
**Library:** `yt-dlp` (Python CLI; supports TikTok, YouTube, Instagram, Facebook)

Steps:
1. Receive job with video URL
2. Call `yt-dlp` to download video file + extract metadata (title, description/caption, uploader, duration)
3. Upload video file to S3; store S3 key in job metadata
4. Write post description + metadata to PostgreSQL `jobs` table
5. Trigger Worker 2 by updating job status and adding to `transcription` queue

**Platform notes:**
- YouTube: most reliable; use YouTube Data API v3 for richer description
- TikTok: yt-dlp works for public videos; no official API for video download
- Instagram/Facebook: yt-dlp handles public posts; Meta restricts API access for video content

#### Worker 2 — Transcription
**Service:** OpenAI Whisper API (`whisper-1` model)

Steps:
1. Download video from S3 (or pass the audio-extracted stream)
2. Extract audio track (ffmpeg: `mp4 → mp3`)
3. Submit audio to Whisper API (max 25 MB; chunk longer videos)
4. Store raw transcription text in PostgreSQL `jobs.transcription`
5. Trigger Worker 3

**Cost estimate:** ~$0.006/minute of audio. A 10-minute cooking video ≈ $0.06.

#### Worker 3 — Recipe AI Extraction
**Service:** OpenAI GPT-4o or Claude (Anthropic)

Steps:
1. Read `jobs.description` and `jobs.transcription` from DB
2. Send a structured prompt:
   ```
   You are a recipe extraction assistant.
   Post description: {description}
   Video transcription: {transcription}
   
   Extract a complete recipe in JSON format with:
   - title (string)
   - servings (string)
   - prep_time, cook_time (strings)
   - ingredients (array of { amount, unit, item })
   - steps (ordered array of strings)
   - notes (optional string)
   
   Reconcile any differences between the description and transcription.
   Prefer the more detailed source for each field.
   ```
3. Parse JSON response; validate required fields
4. Save structured recipe to PostgreSQL `recipes` table
5. Update job status to `completed`; store `recipe_id`

**Cost estimate:** ~$0.002 per extraction (GPT-4o pricing at ~500 input tokens + 300 output tokens).

**Total per recipe:** ~$0.01–$0.08 depending on video length.

---

## 4. Data Model

```sql
-- Users
CREATE TABLE users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       TEXT UNIQUE NOT NULL,
  name        TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Processing Jobs
CREATE TABLE jobs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID REFERENCES users(id) ON DELETE CASCADE,
  url            TEXT NOT NULL,
  platform       TEXT,                  -- 'youtube' | 'tiktok' | 'instagram' | 'facebook'
  status         TEXT DEFAULT 'pending', -- pending | ingesting | transcribing | extracting | completed | failed
  error          TEXT,
  video_s3_key   TEXT,
  description    TEXT,
  transcription  TEXT,
  recipe_id      UUID,
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ DEFAULT now()
);

-- Recipes
CREATE TABLE recipes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
  job_id      UUID REFERENCES jobs(id),
  title       TEXT NOT NULL,
  servings    TEXT,
  prep_time   TEXT,
  cook_time   TEXT,
  ingredients JSONB NOT NULL,   -- [{ amount, unit, item }]
  steps       JSONB NOT NULL,   -- [string]
  notes       TEXT,
  source_url  TEXT,
  source_platform TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_recipes_user_id ON recipes(user_id);
```

---

## 5. Tech Stack Summary

| Layer           | Choice             | Rationale |
|-----------------|--------------------|-----------|
| Web frontend    | React + Vite       | Ecosystem, reusable with React Native |
| Android app     | React Native       | ~80% code shared with web |
| API server      | Node.js + Fastify  | Low latency, same language as frontend |
| Job queue       | Redis + BullMQ     | Simple, battle-tested, good UI (Bull Board) |
| Video download  | yt-dlp (Python)    | Only tool that reliably handles all 4 platforms |
| Transcription   | OpenAI Whisper     | Best accuracy, affordable |
| Recipe AI       | GPT-4o or Claude   | Both work; Claude tends to produce cleaner JSON |
| Database        | PostgreSQL         | JSONB for ingredients/steps, relational for users/jobs |
| File storage    | AWS S3 / Cloudflare R2 | R2 has no egress cost (better for video files) |
| Hosting (API)   | Railway or Render  | Simple deployment, auto-scaling |
| Hosting (web)   | Vercel             | Free tier, edge CDN |

---

## 6. Scale & Reliability

### Load Estimates (v1 public launch)
- 10,000 video submissions/day → ~7 jobs/minute average, ~50/minute peak
- Each job takes 60–180 seconds of pipeline time
- Need ~5 worker instances to handle peak load comfortably

### Scaling Strategy
- Workers are stateless → scale horizontally (add more worker processes/containers)
- Redis queue is the single bottleneck; use Redis Cluster if queue depth > 100k
- PostgreSQL handles this load easily on a single instance (RDS db.t3.medium)
- S3/R2 scales infinitely

### Failure Handling
- BullMQ retries failed jobs up to 3 times with exponential backoff
- yt-dlp failures (platform blocks, deleted video) → job marked `failed` with user-visible error
- Whisper API failures → retry; fall back to description-only extraction if transcription fails after 3 attempts
- "Graceful degradation": if transcription fails, Recipe AI can still extract from the description alone

### Video Storage Cost
- 10,000 videos/day × 100 MB avg = 1 TB/day ingested
- Option A: Store videos indefinitely → ~$20/TB/month on Cloudflare R2
- Option B (recommended for v1): Delete video files after successful transcription; only keep the recipe data. Saves ~$20/TB and avoids copyright storage concerns.

---

## 7. Trade-off Analysis

| Decision | Alternative | Trade-off |
|---|---|---|
| Async queue instead of sync processing | Sync (user waits) | Queue adds complexity but is required for 60–180s jobs; sync would time out HTTP connections |
| yt-dlp for all platforms | Per-platform official APIs | Official APIs (YouTube Data API) give richer metadata but TikTok/Instagram have no public video download API; yt-dlp covers all 4 |
| Delete video after transcription | Keep forever | Saves cost and avoids DMCA risk; downside: can't re-transcribe if Whisper improves |
| Store ingredients/steps as JSONB | Normalized tables | JSONB is far simpler to query and update for this use case; normalized structure only pays off if you need cross-recipe ingredient indexing (post-v1) |
| Node.js API + Python workers | All Python (FastAPI) | Node is ideal for the thin API layer; Python is needed for yt-dlp; mixed is fine, both communicate via Redis |
| Poll for job status | WebSockets | Polling is simpler to implement for v1; WebSockets give better UX and can be added in v2 |

---

## 8. What to Revisit as the App Grows

1. **WebSocket / push notifications** — replace polling with real-time updates
2. **Search** — add full-text search on recipe titles/ingredients (PostgreSQL `tsvector` or Typesense)
3. **Recipe editing** — let users correct AI extraction mistakes
4. **Re-extraction** — allow re-running the AI on existing jobs when the model improves
5. **Batch import** — let users paste multiple URLs at once
6. **Social features** — share recipes, public recipe books
7. **Cost monitoring** — add per-user spending caps; surface AI cost per recipe in admin dashboard

---

## 9. v1 Build Order (Recommended)

1. Set up PostgreSQL schema + API skeleton (auth + job endpoints)
2. Build yt-dlp ingestion worker (handle all 4 platforms)
3. Integrate Whisper transcription worker
4. Build Recipe AI extraction worker + prompt
5. Web frontend: URL submit + polling + recipe display
6. React Native Android app (reuse web components)
7. Deploy: Railway (API + workers) + Vercel (web) + Cloudflare R2 (storage)
