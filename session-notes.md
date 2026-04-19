# Session Notes — LearnLLM Project

## Table of Contents

1. [Debugging & Deploying the Chatbot on EC2](#session-notes--debugging--deploying-the-chatbot-on-ec2) — Initial EC2 deployment, nginx/backend connectivity, IAM, DynamoDB, guardrails
2. [Strands vs LangChain Deep Dive](#session-notes--strands-vs-langchain-deep-dive) — Comparing the three backend options, memory strategies, intent classification
3. [Tokens, Embeddings & Vectors](#session-notes--tokens-embeddings--vectors) — Core concepts and the client-side tokenizer visualizer
4. [Switching Backends + Real Token Counts](#session-notes--switching-backends--real-token-counts) — Moving back to LangChain backend, wiring Bedrock token usage through to UI, model compatibility, distillation

---

# Session Notes — Debugging & Deploying the Chatbot on EC2

## What We Started With

A chatbot app (FastAPI + Python) deployed on EC2 via Terraform, but completely broken. Users hitting the frontend got errors.

## Architecture

```
User → CloudFront → ALB → Nginx (frontend EC2, port 80) → FastAPI/Uvicorn (backend EC2, port 8000) → Bedrock / DynamoDB
```

This is different from the original lab design which uses Lambda + API Gateway + CDK. We use Terraform + EC2 instead. The Python chat code is the same either way.

## Issues We Fixed (in order)

### 1. Nginx → Backend: Connection Refused (error 111)
- Nginx couldn't reach the backend on port 8000
- Security groups were fine — the backend process just wasn't running
- `uvicorn` had `reload=True` in `index.py`, which is a dev feature that watches files for changes
- After startup, it detected file changes (`.pyc` files being created) and killed itself to reload
- The pm2 process manager lost track of it

### 2. .env Not Loading (empty region, empty table name)
- `index.py` called `load_dotenv()` AFTER importing `chat.handler`
- `handler.py` reads env vars at import time (`AWS_REGION = os.environ.get(...)`)
- So all env vars were empty when handler.py loaded them
- Fix: move `load_dotenv()` before the chat imports in `index.py`

### 3. No AWS Credentials
- `botocore.exceptions.NoCredentialsError`
- The IAM instance profile wasn't attached to the EC2 instance
- IMDSv2 was required — confirmed metadata service was reachable but returned 404 on `iam/security-credentials/`
- Fix: attach the instance profile to the EC2 instance

### 4. Empty Region in Bedrock Endpoint
- Error: `Invalid endpoint: https://bedrock-runtime..amazonaws.com` (double dot, no region)
- Caused by issue #2 — AWS_REGION was empty
- Also: boto3 uses `AWS_DEFAULT_REGION`, not `AWS_REGION`
- Fix: add `AWS_DEFAULT_REGION=us-east-1` to `.env`

### 5. DynamoDB Access Denied
- The IAM policy only allowed access to the Terraform-created table (`demo-project-ChatSessions`)
- But `handler.py` had a hardcoded fallback table name (`BurnerGenaiPythonLambdaKrobrian20250828-ChatSessions`) in `us-west-2`
- Fix: widened the DynamoDB IAM policy in `main.tf` to cover `*-ChatSessions` tables

### 6. Guardrails Error on Empty Config
- `.env` had `GUARDRAIL_ID=` (empty)
- The skip check in `handler.py` only matched the literal string `"fake-guardrail-id"`, not empty string
- So it tried to call Bedrock guardrails with an empty ID
- Fix: set `GUARDRAIL_ID=fake-guardrail-id` in `.env` to trigger the skip

## Key Concepts We Discussed

### RAG (Retrieval-Augmented Generation)
- NOT "user uploads files to chat"
- Documents are pre-loaded into a Bedrock Knowledge Base by an admin
- When a user asks a knowledge question (QUERY intent), the retriever searches the KB for relevant chunks
- Those chunks are sent as context to the LLM along with the question
- The LLM answers based on those documents
- Without a Knowledge Base ID configured, QUERY intent fails (CHAT intent still works)

### Intent Classification
- CHAT = conversational ("hello", "thanks") → goes to simple chat chain, no KB lookup
- QUERY = knowledge question ("what is AWS Lambda?") → goes to RAG chain with KB retrieval
- The classifier is an LLM call itself — it asks Claude to categorize the message

### window_size=15
- Each request sends the last 15 messages from the session as conversation history to the LLM
- Older messages are still in DynamoDB but the LLM doesn't see them
- Tradeoff: smaller window = cheaper (fewer input tokens), but bot forgets earlier context
- This is NOT the same as "context window" (200K tokens for Claude 3.5 Haiku) — that's the model's hard limit

### Context Window vs window_size
- Context window = the room (200K tokens, fixed by the model)
- window_size = how many chairs you put in the room (your choice, 15 messages)

### Billing
- Chatbot tokens (Bedrock) → billed to your AWS account
- Kiro credits → billed to your Kiro subscription
- Completely separate. Your end users only cost you Bedrock tokens.

### pm2 Commands
```bash
# Start the backend
cd /opt/app/server/bedrock
sudo PM2_HOME=/etc/.pm2 pm2 start index.py --name bedrock-api --interpreter /opt/app/server/bedrock/venv/bin/python3

# Save process list (survives reboot)
sudo PM2_HOME=/etc/.pm2 pm2 save

# View logs
sudo PM2_HOME=/etc/.pm2 pm2 logs bedrock-api --lines 30

# Restart
sudo PM2_HOME=/etc/.pm2 pm2 restart bedrock-api
```

- `PM2_HOME=/etc/.pm2` tells pm2 where its config lives (set up by user_data as root)
- `--interpreter` points to the venv Python so packages are found
- pm2 is fine for a lab, but production would use systemd or containers

## Current State
- Chatbot is running and responding to CHAT intent messages
- DynamoDB persistence works — messages are saved and conversation history loads
- QUERY/RAG intent fails because no Knowledge Base is configured (expected)
- Guardrails are skipped (no guardrail configured)


---

# Session Notes — Strands vs LangChain Deep Dive

## What We Explored

Walked through the Strands backend (`server/strands/bedrock/`) and compared it to the LangChain backend (`server/bedrock/`).

## Three Backend Options in This Repo

| Server | Framework | Memory | Storage | Frontend compatible? |
|---|---|---|---|---|
| `server/bedrock/index.py` | FastAPI + LangChain | Yes (hybrid chain + DynamoDB) | DynamoDB | Yes |
| `server/strands/bedrock/app.py` | Flask + Strands | No | None | No |
| `server/strands/bedrock/app_with_memory.py` | Flask + Strands | Yes (sliding window) | Local JSON files | No |

## Strands Agent — Not Actually Agentic

The Strands `Agent` class is used here purely as a Bedrock chat client. No tools registered, no `@tool` decorators, no function calling. Just `agent("message")` → get response. The class is called "Agent" but it's acting as a simple chat wrapper.

## Sliding Window Memory — Two Approaches

### LangChain (DynamoDB + window)
- All messages saved to DynamoDB (full history, forever)
- When calling the LLM, `memory.py` fetches all messages from DynamoDB, chain sends last 15 to Bedrock
- DynamoDB query has no `Limit` — fetches everything then slices. Could be optimized.
- Full history available for `/api/chat/history` endpoint and UI display

### Strands (RAM + local files)
- `SlidingWindowConversationManager(window_size=10)` keeps last 10 in RAM
- `FileSessionManager` persists to local JSON files
- Older messages are dropped — lossy. Once they slide out, they're gone.

## Intent Classification Flow

1. User sends message
2. Claude classifies it (extra LLM call): "Is this CHAT or QUERY?"
3. CHAT → conversation chain (no Knowledge Base lookup)
4. QUERY → RAG chain (searches Bedrock Knowledge Base, sends docs + question to Claude)
5. Purpose: avoid unnecessary KB lookups for casual messages like "thanks" or "hello"

The Strands version has no intent classification — everything goes straight to the agent.

## Frontend vs Backend Mismatch

The frontend (`chat-api.ts`) was built for the LangChain backend:

- Sends: `{ "message": "hello", "session_id": null }` (singular string, implicit user role)
- Expects: JSON response with `data.messages` array and `data.session_id`

The Strands `app.py` expects:
- Receives: `{ "messages": [{"role": "user", "content": "hello"}] }` (OpenAI convention, explicit role)
- Returns: SSE stream (`data: {"text": "chunk"}\n\n`)

Two mismatches: request shape and response format. To use Strands with the existing UI, either adapt the backend or rewrite the frontend.

## app.py Ignores Most of Its Input

Despite accepting a `messages` array, `app.py` only uses `messages[-1]['content']`. The rest of the array is thrown away. It's stateless — no memory, no session, every call is independent.

## Framework Comparison

- Flask ≈ Express (minimal, no opinions)
- FastAPI ≈ Express + TypeScript + Swagger (validation, auto-docs, async built in)

## Full Feature Comparison

| | LangChain (`server/bedrock/`) | Strands (`server/strands/bedrock/`) |
|---|---|---|
| LLM call | `ChatBedrockConverse` via LangChain chain | `Agent` via Strands SDK |
| Storage | DynamoDB | Local JSON files (or none) |
| Memory | Full history in DynamoDB, last 15 sent to LLM | Sliding window in RAM (lossy) |
| Intent classification | Yes — Claude classifies CHAT vs QUERY | No |
| RAG | Yes — Bedrock Knowledge Base retriever | No |
| Guardrails | Bedrock Guardrails on input and output | Model-level only |
| Response format | JSON | SSE |
| Frontend compatible? | Yes | No |

## Terraform Update

Updated `main.tf` backend EC2 user_data to deploy `server/strands/bedrock/app.py` instead of `server/bedrock/index.py`. Changed clone path, requirements, .env, and pm2 command.

## Root `chat/` vs `server/bedrock/chat/`

Nearly identical. The `server/bedrock/chat/` version adds `TokenUsage` to the response model and uses empty string defaults for env vars (reads from `.env`). The root `chat/` has hardcoded fake defaults for teaching purposes.

## Can Strands Use DynamoDB?

Yes. You'd save messages to DynamoDB before/after each agent call (outside of Strands), while keeping `SlidingWindowConversationManager` for what the LLM sees. Storage and memory strategy are independent concerns.


---

# Session Notes — Tokens, Embeddings & Vectors

## The Pipeline: Text → Numbers

LLMs can't read words. Everything gets converted to numbers before the model can process it. The pipeline is:

```
Text → Tokens (split + assign IDs) → Embeddings (meaningful number arrays)
```

## Tokens

Tokenization is the first step. A tokenizer breaks text into smaller pieces (words, subwords, or characters) and assigns each piece a numeric ID from its vocabulary.

Example: `"unhappiness"` → `["un", "happi", "ness"]` → `[432, 8821, 1057]`

- Real tokenizers (tiktoken, sentencepiece) use subword tokenization (BPE — Byte Pair Encoding)
- The tokenizer's vocabulary is literally a dict: `{"un": 432, "happi": 8821, "ness": 1057}`
- Different models have different tokenizers and vocabularies

## Embeddings

Once you have token IDs, each one gets mapped to an embedding — a dense array of numbers that represents its meaning.

Token ID `8821` ("happi") → `[0.12, -0.45, 0.78, 0.33, ...]` (hundreds or thousands of dimensions)

- Similar meanings end up close together in this number space ("king" and "queen" are near each other)
- Embeddings are learned during training — the model figures out what numbers best capture meaning
- Not unique to LLMs — embeddings are used across ML for text, images, audio, etc.

## Vectors

A vector is just the math term for an ordered array of numbers: `[0.12, -0.45, 0.78, 0.33, ...]`

- An embedding IS a vector — "embedding" = the learned representation, "vector" = the data structure it lives in
- Think Python `list[float]` or a NumPy array, NOT a dict
- Vectors have direction and magnitude in high-dimensional space
- Similarity between vectors is measured using cosine similarity or Euclidean distance

## Analogy

- Tokens = breaking a sentence into puzzle pieces and labeling each piece with a number
- Embeddings = giving each piece a GPS coordinate in "meaning space"
- Vectors = the GPS coordinate format itself (a list of numbers)

## What We Built

Added a client-side token visualizer to the chat UI:

- Created `src/lib/tokenizer.ts` — simple word-level tokenizer that hashes words to consistent numeric IDs (0–50000 range)
- Updated `src/components/chat/ChatMessage.tsx` — each user message now has a collapsible "Show tokens" toggle
- Clicking it reveals a dict-style view: `{ "hello": 26544, "world": 4891 }`
- This is a simplified word-level tokenizer for learning purposes — real LLM tokenizers use subword tokenization (BPE)

### Files Changed
- `src/lib/tokenizer.ts` (new)
- `src/components/chat/ChatMessage.tsx` (modified)


---

# Session Notes — Switching Backends + Real Token Counts

## Goal

Switch EC2 deployment from Strands back to the LangChain/FastAPI backend (`server/bedrock/`) — the one the frontend was actually built for — and wire real Bedrock token counts through to the UI.

## Issues Hit Along the Way

### 1. `BotocoreConfig` Import Error (Strands backend)
- `app.py` had `from botocore.config import BotocoreConfig` — wrong class name
- Actual class is just `Config`, not `BotocoreConfig`
- Fix: `from botocore.config import Config as BotocoreConfig`

### 2. Hardcoded Fallback Table Name
- `handler.py` had `os.environ.get("CHAT_SESSIONS_TABLE_NAME", "BurnerGenaiPythonLambdaKrobrian20250828-ChatSessions")`
- Also had `AWS_REGION` default of `us-west-2`
- Even after the `.env` fix, these baked-in defaults caused wrong-region/wrong-table errors if the env vars didn't load
- Fix: updated defaults to `demo-project-ChatSessions` and `us-east-1`

### 3. `.env` Heredoc Indentation
- In `main.tf` user_data, the inner `<<ENVFILE` heredoc had leading spaces
- Python `dotenv` can't parse `              KEY=value` lines — whitespace breaks it
- Outer `<<-EOF` strips tabs but not the inner heredoc's content
- Fix: left-align the inner heredoc lines so `.env` has clean `KEY=value` entries

### 4. `load_dotenv()` After Imports
- Same bug as session 1 — `index.py` imported `chat.handler` BEFORE calling `load_dotenv()`
- `handler.py` reads env vars at module import time, so they were empty when loaded
- Fix: move `load_dotenv()` ABOVE the chat module imports

### 5. Overly Narrow DynamoDB IAM Policy
- Policy was scoped to the exact Terraform table ARN
- Fallback code used a different table name → `AccessDeniedException`
- Fix: widened to `arn:aws:dynamodb:*:*:table/*` (fine for a lab, too broad for prod)

### 6. `top_p` Not Supported by All Models
- `chain.py` and `hybrid_chain.py` passed `top_p: 0.9` to `ChatBedrockConverse`
- Amazon Nova models reject `top_p` with `ValidationException: extraneous key [top_p] is not permitted`
- Fix: conditionally include `top_p` only when model ID doesn't contain "nova"

## Real Token Counts — The Refactor

### The Problem
- Backend used `StrOutputParser()` at end of the LangChain chain, which discards the full `AIMessage` and keeps only the string
- The `usage_metadata` attribute (with `input_tokens` / `output_tokens`) was being thrown away

### The Fix — Full Pipeline
1. **`chain.py`**: removed `StrOutputParser()`, `process_message()` now returns `{"text", "input_tokens", "output_tokens"}`
2. **`hybrid_chain.py`**: passes token counts through from chain to handler
3. **`models.py`**: added `input_tokens` / `output_tokens` fields to `ChatResponse`
4. **`handler.py`**: includes token counts in the response
5. **`chat-api.ts`**: reads token counts from JSON response, passes to `onDone` callback
6. **`Chat.tsx`**: stores token counts in state, passes to `ChatInput`
7. **`ChatInput.tsx`**: displays `⚡ 2.52s  📥 Input: 66 tokens  📤 Output: 12 tokens`

### Key Discovery — `usage_metadata` vs `response_metadata`
LangChain's `AIMessage` has TWO metadata attributes:
- `response_metadata` — raw provider response (ResponseMetadata, stopReason, etc.) — NO tokens here
- `usage_metadata` — standardized token info `{input_tokens, output_tokens, total_tokens}`

Initial attempt used `response_metadata.usage` which didn't exist. Debug logging revealed `usage_metadata` as the right attribute.

## Concepts Discussed

### Tokens — Real vs Ours
- Our `tokenizer.ts` is a learning tool — simple word hash to 0–50000 range
- Real LLM tokenizers use BPE/subword — "unhappiness" → `["un", "happi", "ness"]`
- Each model has its own tokenizer; same text tokenizes differently across models

### Can You See What Tokens Claude Uses?
- **No.** Bedrock tells you the count (e.g., "12 tokens") but not the breakdown
- Anthropic hasn't published Claude's tokenizer
- For exact splits, you'd need an open model: Llama, Mistral, or anything from HuggingFace where the tokenizer is public

### Tokenizer Visibility by Model
- **OpenAI (GPT-4, etc.)** — `tiktoken` is public, exact splits available
- **Llama / Mistral / open-source** — SentencePiece tokenizer downloadable
- **Claude (Anthropic)** — closed, count only
- **Amazon Nova** — closed, count only

### Distillation
- Does NOT require access to the teacher's tokens or embeddings
- Student model learns from (prompt, teacher's response text) pairs
- Student uses its own tokenizer — totally independent
- Bedrock Model Distillation handles this as a managed service
- Advanced techniques (logit distillation, soft labels) need model internals but aren't available for closed models

## Restart/Rebuild Commands

### Backend EC2 (FastAPI + pm2)
```bash
cd /opt/app
sudo git pull
sudo PM2_HOME=/etc/.pm2 pm2 restart bedrock-api
sudo PM2_HOME=/etc/.pm2 pm2 logs bedrock-api --lines 30
```

### Frontend EC2 (React + nginx)
```bash
cd /opt/app
sudo git pull
sudo npm run build
sudo systemctl restart nginx
```
Static files live in `/opt/app/dist` — nginx serves those directly, no process to restart for code changes. `npm run build` compiles TS/React into the bundle.

### PM2 Quirk — `PM2_HOME`
- pm2 stores config in `~/.pm2` by default (per-user)
- user_data runs as root → saves to `/root/.pm2`
- SSM session runs as different user → looks at wrong folder → "no processes"
- Fix: always run with `sudo PM2_HOME=/etc/.pm2 pm2 ...` so everyone sees the same process list

## Non-Fatal Errors You'll Still See

These don't block responses, logged for transparency:

- **Retriever 404** — no Knowledge Base configured (`KNOWLEDGE_BASE_ID` empty). The retriever returns empty docs, LLM answers without context. Expected.
- **Guardrails `KeyError: 'action'`** — `GUARDRAIL_ID=fake-guardrail-id` triggers the skip check, but the fake response doesn't have the expected `action` key. Error caught, flow continues.

## Files Changed This Session

- `server/bedrock/index.py` — moved `load_dotenv()` before chat imports, `reload=False`
- `server/bedrock/chat/handler.py` — updated default table/region/model
- `server/bedrock/chat/chain.py` — removed `StrOutputParser`, returns dict with token usage, conditional `top_p`
- `server/bedrock/chat/hybrid_chain.py` — passes token usage through, conditional `top_p`
- `server/bedrock/chat/models.py` — added token fields to `ChatResponse`
- `server/strands/bedrock/app.py` — fixed `BotocoreConfig` import
- `infra_terraform/main.tf` — switched user_data to bedrock backend, broadened DynamoDB IAM, inline `.env` creation
- `src/lib/chat-api.ts` — reads token counts from response, new `TokenUsage` type
- `src/pages/Chat.tsx` — token state, passes to `ChatInput`
- `src/components/chat/ChatInput.tsx` — displays input/output token counts alongside response time
