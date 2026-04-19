# Tech Debts — LearnLLM Project

A running log of things that work today but will bite us at scale, with file references and concrete fixes. Ordered roughly by blast radius at 1M users.

## Table of Contents

1. [Compute & Deployment](#compute--deployment)
2. [Backend Runtime (Bedrock variant)](#backend-runtime-bedrock-variant)
3. [Data Layer — DynamoDB](#data-layer--dynamodb)
4. [Caching — missing entirely](#caching--missing-entirely)
5. [Auth & Multi-Tenancy](#auth--multi-tenancy)
6. [Frontend](#frontend)
7. [LLM Cost & Throughput](#llm-cost--throughput)
8. [Observability](#observability)
9. [Infrastructure (Terraform)](#infrastructure-terraform)
10. [Minor / Cleanup](#minor--cleanup)

---

## Compute & Deployment

### 1. Single EC2 backend, no autoscaling
- **Where**: `infra_terraform/main.tf` — `aws_instance.backend`, `t3.medium`, `count = var.create_vpc ? 1 : 0`
- **Problem**: one box in one AZ. ~100–300 concurrent long LLM calls before CPU/memory tips over. No failover.
- **Fix**: ECS Fargate behind an internal ALB, autoscale on `ALB RequestCountPerTarget` + CPU. Min 3 / max ~200 tasks across 2+ AZs.

### 2. Backend in a public subnet
- **Where**: `infra_terraform/main.tf` — `subnet_id = aws_subnet.public_subnet_01[0].id`
- **Problem**: backend is internet-addressable for no reason.
- **Fix**: move to private subnets, NAT gateway (or better, VPC endpoints for DynamoDB + Bedrock) for egress.

### 3. Frontend served from EC2 + nginx
- **Where**: frontend EC2 in `main.tf`, nginx proxying static assets
- **Problem**: EC2 for static files is waste at any non-trivial scale.
- **Fix**: Vite build → S3 + CloudFront. Kill the frontend EC2.

### 4. pm2 as process supervisor
- **Where**: user_data in `main.tf`, `PM2_HOME=/etc/.pm2`
- **Problem**: fine for a lab, poor fit for fleets (no rolling deploys, no health signals to ALB).
- **Fix**: containerize (Dockerfile next to `server/bedrock/`), run under ECS with ALB health checks hitting `/` or a dedicated `/healthz`.

---

## Backend Runtime (Bedrock variant)

### 5. Sync Bedrock calls inside async FastAPI
- **Where**: `server/bedrock/chat/chain.py` — `ChatBedrockConverse(...).invoke(...)`, same in `hybrid_chain.py`
- **Problem**: `invoke()` is blocking. Under async FastAPI one slow call stalls the event loop for every other request on that worker.
- **Fix**: use `astream` / `ainvoke`, stream tokens out via `StreamingResponse` (SSE). Alternative: wrap sync call in `asyncio.to_thread` with a bounded semaphore.

### 6. Response is not streamed to the client
- **Where**: `src/lib/chat-api.ts` — `const data = await response.json()`; backend returns full JSON in `handler.py`
- **Problem**: users wait for the full completion before seeing anything. Perceived latency is 3–5x worse than it needs to be, and connections hold longer (hurts concurrency).
- **Fix**: SSE end-to-end. `ollama/index.py` already shows the `StreamingResponse` pattern.

### 7. boto3 clients built at import without retry/pool tuning
- **Where**: `server/bedrock/chat/handler.py` — top-level `boto3.client(...)` / `boto3.resource(...)`
- **Problem**: default connection pool = 10, default retry mode is legacy. Under load you'll see throttles and connection reuse starvation.
- **Fix**:
  ```python
  from botocore.config import Config
  cfg = Config(retries={"max_attempts": 5, "mode": "adaptive"}, max_pool_connections=50)
  bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=cfg)
  ```

### 8. Singleton `hybrid_chain` at module import
- **Where**: `server/bedrock/chat/handler.py` — `hybrid_chain = HybridConversationChain(...)` at import time
- **Problem**: fine for one worker, but module-level state means no per-request config (tenant, model override, etc.) and harder to test.
- **Fix**: build the chain in an app-scoped factory, inject via FastAPI `Depends`. Keep it cached per-process.

### 9. Intent classifier is an extra LLM call per message
- **Where**: `server/bedrock/chat/classifier.py` used by `hybrid_chain.py`
- **Problem**: doubles Bedrock RPS and adds latency for every turn — even "thanks".
- **Fix**: short-circuit with a cheap heuristic first (length + regex for question words). Fall through to LLM classifier only on ambiguity. Or use a tiny distilled model.

### 10. No request-level timeout or circuit breaker on Bedrock
- **Where**: `chat/chain.py`, `chat/retriever.py`
- **Problem**: a slow/hung Bedrock call can pin a worker indefinitely.
- **Fix**: `asyncio.wait_for` with a hard ceiling (e.g. 30s), plus a circuit breaker (e.g. `purgatory` / `pybreaker`) around Bedrock to fail fast during regional issues.

### 11. slowapi rate limiter is in-process only
- **Where**: `server/ollama/index.py` uses `slowapi` keyed by remote address
- **Problem**: doesn't work across multiple tasks — each instance has its own counter, and the key is IP (broken behind ALB/CloudFront).
- **Fix**: Redis-backed token bucket keyed by authenticated `user_id`. Put real client IP in an `X-Forwarded-For` chain you trust.

---

## Data Layer — DynamoDB

### 12. `get_messages` returns the full session history every request
- **Where**: `server/bedrock/chat/repository.py` — `Query` with no `Limit`, ascending order
- **Problem**: 1,000-message sessions cost the whole table read every turn. Latency + RCU blow up.
- **Fix**: `Limit=window_size*2`, `ScanIndexForward=False`, reverse in memory. Paginate for `/api/chat/history` via `LastEvaluatedKey`.

### 13. No TTL on chat sessions
- **Where**: `MessageRepository.save_message` writes `timestamp` but no `ttl`
- **Problem**: storage grows forever; no easy way to honor retention/privacy promises.
- **Fix**: add `ttl` attribute (epoch seconds, e.g. now + 90 days), enable DynamoDB TTL on the table.

### 14. No `user_id` in the schema
- **Where**: table PK `session_id`, SK `message_id` — nowhere does a user own a session
- **Problem**: any client that guesses/steals a `session_id` reads the session. Multi-tenant isolation is impossible.
- **Fix**: PK `user_id`, SK `session_id#message_id` (or composite attribute). GSI on `user_id` for "my sessions" listings. Backfill existing rows.

### 15. No pagination on `/api/chat/history`
- **Where**: `server/bedrock/chat/handler.py` — `get_session_history_handler`
- **Problem**: endpoint returns everything. One large session = large payload + slow render.
- **Fix**: cursor-based pagination (`next_token` from `LastEvaluatedKey`), page size cap.

### 16. Broad DynamoDB IAM policy
- **Where**: `infra_terraform/main.tf` — policy widened to `arn:aws:dynamodb:*:*:table/*` during lab debugging
- **Problem**: over-privileged. Fine for a lab, unacceptable for prod.
- **Fix**: scope back to the specific table ARN(s) + their indexes.

---

## Caching — missing entirely

### 17. No Redis / ElastiCache
- **Where**: absent from `main.tf` and the code
- **Problem**: every turn re-reads DynamoDB for the conversation window, re-hits Bedrock KB for the same questions, and rate limiting can't be distributed.
- **Fix**: add ElastiCache Redis. Use for:
  - session window cache (write-through on save, read-through on fetch, keyed by `session_id`)
  - per-user rate limits (token bucket)
  - idempotency keys for retries

### 18. No semantic/prompt cache for Bedrock
- **Where**: `chat/retriever.py` + `chat/chain.py`
- **Problem**: identical or near-identical questions each cost a full Bedrock round-trip.
- **Fix**:
  - Prompt caching on Bedrock for the static system prompt + retrieved context block
  - Redis cache keyed by hash of (normalized question + top-k KB doc ids) with short TTL for FAQ-style traffic

---

## Auth & Multi-Tenancy

### 19. No authentication on any endpoint
- **Where**: `server/bedrock/index.py` — CORS is the only gatekeeper
- **Problem**: anyone can call `/api/chat` and spend your Bedrock budget.
- **Fix**: API Gateway in front of ALB with a Cognito / JWT authorizer. Propagate `user_id` into the request scope.

### 20. `allow_credentials=True` with env-list origins
- **Where**: `server/bedrock/index.py` — `CORSMiddleware(..., allow_credentials=True, allow_origins=ALLOWED_ORIGINS)`
- **Problem**: OK today because the list is explicit, but easy to regress to `*` which silently breaks credentials and is a CSRF risk.
- **Fix**: keep the allow-list strict, add a startup assertion that rejects `*` when `allow_credentials=True`.

### 21. No per-user rate limiting or quota
- **Where**: n/a — not implemented in the bedrock variant
- **Problem**: a single bad actor can drain Bedrock TPM.
- **Fix**: Redis token bucket keyed by `user_id` + tier (free/paid). WAF rate-based rules as the outer perimeter.

### 22. No input validation on message size
- **Where**: `server/bedrock/chat/models.py` — `ChatRequest.message` is an unconstrained string
- **Problem**: a 1MB message wastes tokens, DynamoDB write capacity, and can trip Bedrock limits.
- **Fix**: `Field(..., min_length=1, max_length=4000)` like `server/ollama/index.py` already does.

---

## Frontend

### 23. Sessions only in `localStorage`
- **Where**: `src/lib/session-storage.ts`, consumed in `src/pages/Chat.tsx`
- **Problem**: clear browser = lose all sessions. No cross-device sync. No backend validation that a session belongs to the user.
- **Fix**: once auth lands, hydrate the sidebar from `/api/chat/history` using the user's JWT. `localStorage` becomes a cache only.

### 24. `currentSessionId` is a module-level `let`
- **Where**: `src/lib/chat-api.ts` — top-level `let currentSessionId`
- **Problem**: one global per tab. If we ever add multi-tab multi-session or tests, this is a foot-gun.
- **Fix**: move into a React context / store (Zustand, or TanStack Query's cache).

### 25. No retry / backoff on fetch
- **Where**: `src/lib/chat-api.ts` — single `fetch`, no retry
- **Problem**: transient 502 from ALB during a deploy = user sees an error instantly.
- **Fix**: small retry with jittered backoff for idempotent reads (history). Never auto-retry `/api/chat` without an idempotency key (see #17).

### 26. Client-side tokenizer is a toy
- **Where**: `src/lib/tokenizer.ts`
- **Problem**: word-hash → 0–50000. Good for teaching, misleading for real token counts.
- **Fix**: keep as-is for the learning UX, but make sure the "real" token count shown to users comes from Bedrock `usage_metadata` (it does, from the last session's refactor).

---

## LLM Cost & Throughput

### 27. One model for all intents
- **Where**: `chat/hybrid_chain.py` — same `MODEL_ID` for CHAT and QUERY paths
- **Problem**: paying Claude prices for "thanks".
- **Fix**: route CHAT → Nova Lite / Haiku, QUERY → Sonnet (or Haiku for simple RAG). Environment-driven model map.

### 28. Bedrock on-demand only
- **Where**: provisioning in `main.tf` — no Provisioned Throughput
- **Problem**: on-demand TPM/RPM is capped per account-region. At 1M users, throttles are a when-not-if.
- **Fix**: evaluate Provisioned Throughput for baseline + on-demand for spikes. Use cross-region inference model IDs (`us.anthropic.*` — already in use) to spread load.

### 29. Bedrock Guardrails called synchronously twice per message
- **Where**: `chat/handler.py` — `apply_guardrails` on input and output
- **Problem**: two extra sync round-trips per turn.
- **Fix**: run input guardrail concurrently with intent classification; run output guardrail as a streaming interceptor once streaming lands.

---

## Observability

### 30. No tracing, thin metrics
- **Where**: `chat/handler.py` imports `aws_lambda_powertools` but we barely emit anything. No X-Ray.
- **Problem**: at 1M users, "it's slow" is unsolvable without traces.
- **Fix**:
  - EMF metrics per request: latency, input/output tokens, intent, cache hit, Bedrock throttle count
  - X-Ray across API GW → ECS → Bedrock → DynamoDB
  - Alarms: Bedrock throttles, DynamoDB throttles, ALB 5xx, p99 latency, Redis evictions

### 31. Logs go to local files on EC2
- **Where**: `server/ollama/index.py` — `FileHandler(LOG_DIR/...)`; bedrock variant relies on pm2 stdout
- **Problem**: dies with the instance.
- **Fix**: structured JSON logs to stdout only; let ECS/Fargate ship to CloudWatch Logs.

---

## Infrastructure (Terraform)

### 32. No backend health check path
- **Where**: `main.tf` — no `/healthz` target group health check (backend isn't behind an ALB yet)
- **Problem**: ALB can't drain bad tasks.
- **Fix**: add a cheap `GET /healthz` to FastAPI that verifies DynamoDB + Bedrock reachability; wire into ALB target group.

### 33. `.env` rendered inline in user_data
- **Where**: `main.tf` user_data heredoc writes `.env`
- **Problem**: secrets on disk, no rotation, tied to instance boot.
- **Fix**: pull config at boot from SSM Parameter Store or Secrets Manager (via IAM role). Or pass as ECS task definition env from Secrets Manager.

### 34. No WAF
- **Where**: CloudFront in front of ALB, no `aws_wafv2_web_acl`
- **Problem**: no rate-based rules, no bot control, no geo blocking.
- **Fix**: attach WAFv2 to API Gateway / CloudFront with AWS managed rule groups + a rate-based rule.

### 35. Single region
- **Where**: `provider "aws" { region = "us-east-1" }`
- **Problem**: us-east-1 outages take us down entirely.
- **Fix**: for 1M users, plan multi-region active-active (Route 53 latency routing, DynamoDB Global Tables, Bedrock cross-region inference). Treat as Phase 3 — not free.

---

## Minor / Cleanup

### 36. Three backend variants in-tree (`bedrock`, `ollama`, `strands`)
- **Problem**: drift risk, duplicate chat modules, contributors change the wrong one.
- **Fix**: pick `bedrock` as the prod target, mark `ollama` + `strands` clearly as demos in their READMEs, or move them to an `examples/` folder.

### 37. `chat/repository.py` header says "STUDENT IMPLEMENTATION REQUIRED"
- **Problem**: lab artifact in a file we now treat as production code.
- **Fix**: remove the student-guide comments once we're confident in the implementation.

### 38. Hardcoded defaults that leak between environments
- **Where**: `chat/handler.py` defaults like `"us.anthropic.claude-3-5-haiku-20241022-v1:0"`, `"us-east-1"`
- **Problem**: masks missing config. We already got burned by this twice in session notes.
- **Fix**: fail fast — require env vars, log a clear error on startup if unset.

### 39. `PORT = int(os.getenv("PORT", ""))`
- **Where**: `server/bedrock/index.py`
- **Problem**: crashes with `ValueError` if `PORT` is unset instead of giving a default.
- **Fix**: `int(os.getenv("PORT", "8000"))`.

### 40. No tests
- **Where**: repo-wide
- **Problem**: every change is "deploy and hope".
- **Fix**: unit tests for `repository.py`, `classifier.py`, and the hybrid routing logic at minimum. Moto for DynamoDB, recorded fixtures for Bedrock responses.

---

## Prioritized Next Steps

If we only do a handful of things, do these in order:

1. Streaming + async Bedrock (#5, #6) — biggest UX + concurrency win, no infra rewrite
2. boto3 retry/pool config (#7) — one-line changes, meaningful impact
3. Redis session cache + per-user rate limit (#17, #21) — needs ElastiCache, unlocks a lot
4. Fargate + ALB + autoscaling (#1, #2, #4) — the actual horizontal scaling move
5. Cognito auth + `user_id` in DynamoDB schema (#14, #19) — required before "1M users" means anything real
6. Semantic + prompt caching (#18), model routing (#27) — cost control
7. Observability end-to-end (#30) — so we know where the next bottleneck is
