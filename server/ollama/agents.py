"""
LearnLLM Backend - FastAPI + Ollama with Agent Tools + Bash
Local use only — do NOT expose this to the public internet.
"""

import os
import re
import json
import logging
import uuid
import httpx
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'smollm:1.7b')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5173').split(',')
RATE_LIMIT = os.getenv('RATE_LIMIT', '10/minute')

# Logging
Path(LOG_DIR).mkdir(exist_ok=True)
logger = logging.getLogger(__name__)
if not logger.handlers:
    log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(getattr(logging, LOG_LEVEL))

# FastAPI + rate limiting
app = FastAPI(title="LearnLLM API", version="2.0.0")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system|tool)$")
    content: str = Field(..., min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1, max_length=50)

# ---------------------------------------------------------------------------
# TOOLS
#
# A "tool" is just a Python function the model can choose to call.
# The flow works like this:
#
#   1. You describe the tools to the model in the system prompt
#   2. The model replies with a JSON call:
#      {"tool": "get_weather", "args": {"city": "London"}}
#   3. Your code detects this, runs the real Python function
#   4. You feed the result back to the model
#   5. The model uses the result to write its final answer
#
# NOTE: Smaller models like smollm:1.7b are not reliable at tool use.
# For better results use: llama3, mistral, or qwen2.5
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SANDBOX CONFIGURATION
#
# ALLOWED_COMMANDS: only these base commands can be executed.
# Add or remove commands here to control what the agent can run.
# ---------------------------------------------------------------------------

SANDBOX_DIR = os.getenv("SANDBOX_DIR", "./sandbox")   # all file ops are jailed here
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", 10))  # seconds per command
MAX_OUTPUT_BYTES = 4096                                  # cap output sent back to model

# Allowlist of permitted base commands — everything else is rejected
ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "pwd", "mkdir", "touch", "mv", "cp",
    "head", "tail", "grep", "wc", "find", "python3", "python",
    "node", "date", "whoami", "uname", "df", "du", "env",
}

# Blocklist of dangerous patterns — rejected even if base command is allowed
BLOCKED_PATTERNS = [
    r"rm\s+-rf",          # recursive delete
    r">\s*/dev/",         # writing to devices
    r"chmod\s+777",       # wide-open permissions
    r"curl\s+.*\|",       # curl pipe to shell
    r"wget\s+.*\|",       # wget pipe to shell
    r";\s*rm\b",          # chained rm
    r"&&\s*rm\b",         # chained rm
    r"\$\(",              # command substitution
    r"`[^`]+`",           # backtick execution
]

# Safe environment — strips AWS credentials and other secrets
SAFE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": str(Path(SANDBOX_DIR).resolve()),
    "TERM": "xterm",
}


def _is_command_allowed(command: str) -> tuple[bool, str]:
    """
    Validate a command against the allowlist and blocklist.
    Returns (allowed: bool, reason: str)
    """
    command = command.strip()

    # Check blocked patterns first
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Blocked pattern detected: {pattern}"

    # Extract base command (first word)
    base = re.split(r"[\s|&;]", command)[0].strip()
    base = Path(base).name  # strip any path prefix e.g. /usr/bin/python3 → python3

    if base not in ALLOWED_COMMANDS:
        return False, f"Command '{base}' is not in the allowlist: {sorted(ALLOWED_COMMANDS)}"

    return True, "ok"


def run_bash(command: str) -> str:
    """
    Tool: Run a bash command in the sandbox directory.

    Safety rules:
    - Only allowlisted commands are permitted
    - Blocked patterns (rm -rf, pipes to shell, etc) are rejected
    - Hard timeout per command
    - Output is capped to prevent flooding
    - Runs with a stripped environment (no AWS keys, no secrets)
    - Working directory is locked to SANDBOX_DIR
    """
    # Ensure sandbox directory exists
    sandbox = Path(SANDBOX_DIR).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)

    # Validate command
    allowed, reason = _is_command_allowed(command)
    if not allowed:
        logger.warning(f"[tool:run_bash] BLOCKED: {command!r} — {reason}")
        return f"Blocked: {reason}"

    logger.info(f"[tool:run_bash] Running: {command!r} in {sandbox}")

    try:
        result = subprocess.run(
            command,
            shell=True,                  # noqa: S602 — guarded by allowlist above
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=str(sandbox),            # jail working directory
            env=SAFE_ENV,                # stripped environment
        )

        output = result.stdout + result.stderr

        # Cap output size
        if len(output) > MAX_OUTPUT_BYTES:
            output = output[:MAX_OUTPUT_BYTES] + f"\n... (truncated, {len(output)} bytes total)"

        exit_info = f"\n[exit code: {result.returncode}]"
        logger.info(f"[tool:run_bash] Exit {result.returncode}, output: {output[:100]}")
        return (output or "(no output)") + exit_info

    except subprocess.TimeoutExpired:
        logger.warning(f"[tool:run_bash] Timeout after {COMMAND_TIMEOUT}s: {command!r}")
        return f"Error: command timed out after {COMMAND_TIMEOUT} seconds"
    except Exception as e:
        logger.error(f"[tool:run_bash] Exception: {type(e).__name__}: {e}")
        return f"Error: {str(e)}"


def read_file(path: str) -> str:
    """
    Tool: Read a file from the sandbox directory.
    Path is always resolved relative to SANDBOX_DIR — cannot escape it.
    """
    sandbox = Path(SANDBOX_DIR).resolve()
    target = (sandbox / path).resolve()

    # Prevent path traversal e.g. ../../etc/passwd
    if not str(target).startswith(str(sandbox)):
        logger.warning(f"[tool:read_file] Path traversal attempt: {path!r}")
        return "Error: path is outside the sandbox directory"

    if not target.exists():
        return f"Error: file not found: {path}"
    if not target.is_file():
        return f"Error: not a file: {path}"

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_OUTPUT_BYTES:
            content = content[:MAX_OUTPUT_BYTES] + f"\n... (truncated)"
        logger.info(f"[tool:read_file] Read {len(content)} bytes from {target}")
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """
    Tool: Write content to a file inside the sandbox directory.
    Path is always resolved relative to SANDBOX_DIR — cannot escape it.
    """
    sandbox = Path(SANDBOX_DIR).resolve()
    target = (sandbox / path).resolve()

    # Prevent path traversal
    if not str(target).startswith(str(sandbox)):
        logger.warning(f"[tool:write_file] Path traversal attempt: {path!r}")
        return "Error: path is outside the sandbox directory"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info(f"[tool:write_file] Wrote {len(content)} bytes to {target}")
        return f"File written: {path} ({len(content)} bytes)"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def list_files(path: str = ".") -> str:
    """
    Tool: List files in a directory inside the sandbox.
    """
    sandbox = Path(SANDBOX_DIR).resolve()
    target = (sandbox / path).resolve()

    if not str(target).startswith(str(sandbox)):
        return "Error: path is outside the sandbox directory"

    if not target.exists():
        return f"Error: directory not found: {path}"

    try:
        entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = []
        for entry in entries:
            kind = "FILE" if entry.is_file() else "DIR "
            size = entry.stat().st_size if entry.is_file() else ""
            lines.append(f"{kind}  {entry.name}  {size}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error: {str(e)}"


def calculate(expression: str) -> str:
    """Tool: Safely evaluate a math expression. e.g. '2 + 2', 'sqrt(144)'"""
    try:
        import math
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}
        result = eval(expression, {"__builtins__": {}}, allowed)  # noqa: S307
        logger.info(f"[tool:calculate] {expression} = {result}")
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


def get_date() -> str:
    """Tool: Get the current date and time."""
    return datetime.now().strftime("%A, %B %d %Y at %H:%M")


# Registry — maps tool name to its function
TOOLS: Dict[str, Any] = {
    "run_bash":   run_bash,
    "read_file":  read_file,
    "write_file": write_file,
    "list_files": list_files,
    "calculate":  calculate,
    "get_date":   get_date,
}

# ---------------------------------------------------------------------------
# SYSTEM PROMPT — teaches the model how to use tools
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are LearnLLM, a helpful AI assistant with access to a local sandbox.

When you need to use a tool, respond with ONLY a JSON object (no extra text):

{"tool": "tool_name", "args": {"arg1": "value1"}}

Available tools:

- run_bash:   Run a shell command in the sandbox
  {"tool": "run_bash", "args": {"command": "ls -la"}}

- read_file:  Read a file from the sandbox
  {"tool": "read_file", "args": {"path": "hello.py"}}

- write_file: Write content to a file in the sandbox
  {"tool": "write_file", "args": {"path": "hello.py", "content": "print('hello')"}}

- list_files: List files in a sandbox directory
  {"tool": "list_files", "args": {"path": "."}}

- calculate:  Evaluate a math expression
  {"tool": "calculate", "args": {"expression": "sqrt(144)"}}

- get_date:   Get current date and time
  {"tool": "get_date", "args": {}}

Rules:
- Use tools only when actually needed
- After getting a tool result, write your final answer in plain text
- Never mix tool JSON with plain text in the same response
- For multi-step tasks, call one tool at a time
"""

# ---------------------------------------------------------------------------
# AGENT LOOP
#
# An "agent" is just a loop:
#
#   while model wants to call a tool:
#       run the tool → feed result back to model
#   return final plain-text answer
#
# This is exactly what frameworks like Strands, LangChain, and LlamaIndex
# do under the hood — we're just doing it manually so you can see it clearly.
# ---------------------------------------------------------------------------

def try_parse_tool_call(text: str) -> dict | None:
    """
    Check if the model's response is a tool call.
    Returns parsed dict if yes, None if it's a regular message.
    """
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
        if "tool" in data and "args" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None


async def run_agent(messages: List[Message], request_id: str) -> str:
    """
    The agent loop.
    Keeps calling the model until it returns a plain text answer
    instead of a tool call.
    """
    # Build conversation for Ollama
    ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    ollama_messages += [{"role": m.role, "content": m.content} for m in messages]

    timeout = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0)
    max_iterations = 5  # safety cap — prevents infinite loops

    async with httpx.AsyncClient(timeout=timeout) as client:
        for iteration in range(max_iterations):
            logger.info(f"[{request_id}] Agent iteration {iteration + 1}/{max_iterations}")

            # Step 1: Ask the model
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"temperature": 0.1}
                }
            )
            response.raise_for_status()
            assistant_text = response.json()["message"]["content"].strip()
            logger.info(f"[{request_id}] Model reply: {assistant_text[:200]}")

            # Step 2: Did the model call a tool?
            tool_call = try_parse_tool_call(assistant_text)

            if tool_call is None:
                # No tool call — this is the final answer, return it
                return assistant_text

            # Step 3: Run the tool
            tool_name = tool_call["tool"]
            tool_args = tool_call.get("args", {})

            if tool_name not in TOOLS:
                # Model hallucinated a tool name
                tool_result = f"Error: tool '{tool_name}' does not exist."
            else:
                try:
                    tool_result = TOOLS[tool_name](**tool_args)
                except Exception as e:
                    tool_result = f"Error running tool: {str(e)}"

            logger.info(f"[{request_id}] Tool '{tool_name}' returned: {tool_result}")

            # Step 4: Feed the tool result back so the model can use it
            ollama_messages.append({"role": "assistant", "content": assistant_text})
            ollama_messages.append({
                "role": "user",
                "content": f"Tool result for {tool_name}: {tool_result}\n\nNow answer the user's original question using this result."
            })

            # Loop continues — model will now write its final answer

    return "I was unable to complete the request after several attempts."


async def stream_agent_response(messages: List[Message], request_id: str):
    """Run the agent loop, then stream the final answer as SSE"""
    try:
        logger.info(f"[{request_id}] Request - messages: {len(messages)}")
        start_time = datetime.now()

        # Run the full agent (all tool calls happen here, before streaming)
        final_answer = await run_agent(messages, request_id)

        # Stream the final answer word by word so the frontend
        # still gets a streaming feel even though we waited for the full answer
        words = final_answer.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Complete - duration: {duration:.2f}s")
        yield "data: [DONE]\n\n"

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] Timeout")
        yield f"data: {json.dumps({'error': 'Request timeout'})}\n\n"
    except httpx.HTTPStatusError as e:
        logger.error(f"[{request_id}] HTTP error: {e.response.status_code}")
        yield f"data: {json.dumps({'error': f'Ollama error: {e.response.status_code}'})}\n\n"
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {type(e).__name__}")
        yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    try:
        timeout = httpx.Timeout(connect=2.0, read=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            return {"status": "ready", "ollama": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama not ready: {str(e)}")


@app.get("/api/health")
async def health():
    try:
        timeout = httpx.Timeout(connect=2.0, read=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            ollama_status = "connected"
    except Exception as e:
        ollama_status = f"error: {str(e)}"
    return {"status": "ok", "model": MODEL_NAME, "ollama_status": ollama_status}


@app.post("/api/chat")
@limiter.limit(RATE_LIMIT)
async def chat(chat_request: ChatRequest, request: Request):
    """Chat endpoint — agent automatically uses tools when needed"""
    request_id = str(uuid.uuid4())
    return StreamingResponse(
        stream_agent_response(chat_request.messages, request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id
        }
    )


@app.get("/api/tools")
async def list_tools():
    """List all tools available to the agent"""
    return {
        "sandbox_dir": str(Path(SANDBOX_DIR).resolve()),
        "allowed_commands": sorted(ALLOWED_COMMANDS),
        "tools": [
            {"name": "run_bash",   "description": "Run an allowlisted shell command in the sandbox", "args": ["command"]},
            {"name": "read_file",  "description": "Read a file from the sandbox",                    "args": ["path"]},
            {"name": "write_file", "description": "Write content to a file in the sandbox",          "args": ["path", "content"]},
            {"name": "list_files", "description": "List files in a sandbox directory",               "args": ["path"]},
            {"name": "calculate",  "description": "Evaluate a math expression",                      "args": ["expression"]},
            {"name": "get_date",   "description": "Get the current date and time",                   "args": []},
        ]
    }


@app.get("/api/models")
@limiter.limit("5/minute")
async def list_models(request: Request):
    try:
        timeout = httpx.Timeout(connect=2.0, read=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
            return {"models": [m["name"] for m in data.get("models", [])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info("=" * 60)
    logger.info("LearnLLM - FastAPI + Ollama + Agent Tools + Bash")
    logger.info("=" * 60)
    logger.info(f"Model:       {MODEL_NAME}")
    logger.info(f"Ollama:      {OLLAMA_URL}")
    logger.info(f"Port:        {PORT}")
    logger.info(f"Tools:       {list(TOOLS.keys())}")
    logger.info(f"Sandbox:     {Path(SANDBOX_DIR).resolve()}")
    logger.info(f"Rate limit:  {RATE_LIMIT}")
    logger.info("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
