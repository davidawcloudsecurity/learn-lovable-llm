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
