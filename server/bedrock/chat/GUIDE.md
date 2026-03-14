Here's the complete walkthrough of every file and how they connect:

---

## The Full Flow - What happens when you send "What is AWS Lambda?"

```
You type → frontend → POST /api/chat → handler.py
```

---

## Step 1: handler.py - The traffic cop

Receives the request, validates it, coordinates everything:

```python
# Request arrives:
{ "session_id": null, "message": "What is AWS Lambda?" }

# 1. Validate with models.py
# 2. Create or find session
# 3. Apply guardrails (input)
# 4. Call hybrid_chain to get response
# 5. Apply guardrails (output)
# 6. Save to DynamoDB
# 7. Return all messages
```

---

## Step 2: models.py - The data shapes

Just defines what things look like. Think of it as a form template:

```python
ChatRequest  → { session_id, message }
ChatResponse → { session_id, messages[] }
ChatMessage  → { message_id, message_type, message, timestamp, intent, sources }
```

Also generates IDs like `session_01kkn6x5...` and `message_01kkn6y...` using ULID (like UUID but sortable by time).

---

## Step 3: session.py - The session manager

Sits between handler and DynamoDB. Knows about sessions, not about AI:

```python
create_session()          → generates session_id
session_exists(id)        → checks DynamoDB
add_human_message(id, msg) → saves your message
add_bot_message(id, msg)  → saves Claude's reply
get_session(id)           → returns all messages
```

---

## Step 4: repository.py - The database layer

Only talks to DynamoDB. Knows nothing about sessions or AI:

```python
save_message(session_id, message_id, type, content) → DynamoDB PutItem
get_messages(session_id)                            → DynamoDB Query
```

---

## Step 5: hybrid_chain.py - The router

First asks the classifier: is this CHAT or QUERY?

```
"What is AWS Lambda?"  → classifier says QUERY → use RAG chain
"Thanks!"              → classifier says CHAT  → use simple chain
```

---

## Step 6: classifier.py - The intent detector

Sends your message to Claude with a prompt asking "is this CHAT or QUERY?":

```
prompt: "Classify this: 'What is AWS Lambda?'"
Claude: "QUERY"
```

This costs one extra LLM call per message.

---

## Step 7: chain.py - Where the actual AI call happens

Builds the full prompt and calls Claude:

```python
# 1. Load history from memory.py (last 15 messages)
# 2. If QUERY: fetch docs from retriever.py
# 3. Build prompt:
#    [system: "You are helpful. Context: {docs}"]
#    [history: turn1, turn2, turn3...]
#    [human: "What is AWS Lambda?"]
# 4. Send to Claude → get response
```

---

## Step 8: memory.py - The history converter

DynamoDB stores messages like:
```json
{ "message_type": "HUMAN", "message": "hi" }
```

But LangChain/Claude needs:
```python
HumanMessage(content="hi")
AIMessage(content="hello!")
```

`memory.py` converts between these two formats.

---

## Step 9: retriever.py - The knowledge lookup

Only used when intent is QUERY. Searches your Bedrock Knowledge Base:

```python
query: "What is AWS Lambda?"
→ searches vector database
→ returns top 5 relevant document chunks
→ those chunks go into the system prompt as "Context"
```

If no Knowledge Base is configured, it returns empty docs and Claude answers from its training data.

---

## Step 10: exceptions.py - The error types

Just defines named errors so the code is readable:

```python
ChatSessionNotFoundError  → 404
ChatMessageTooLongError   → 400
ChatServiceUnavailableError → 503
GuardrailInterventionError → 400
```

---

## The complete picture

```
Request
  ↓
handler.py        validates input, orchestrates everything
  ↓
session.py        creates/finds session
  ↓
repository.py     saves human message to DynamoDB
  ↓
hybrid_chain.py   routes based on intent
  ↓
classifier.py     asks Claude: CHAT or QUERY?
  ↓
memory.py         loads last 15 messages from DynamoDB
  ↓
retriever.py      (if QUERY) fetches relevant docs
  ↓
chain.py          builds full prompt → calls Claude → gets response
  ↓
handler.py        saves bot response to DynamoDB
  ↓
Response          returns all messages to frontend
```
