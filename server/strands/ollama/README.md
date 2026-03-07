# LearnLLM Backend - Ollama Version

Local LLM backend using Ollama and Strands framework.

## Features

- ✅ Runs locally (no cloud needed)
- ✅ Free (no API costs)
- ✅ Privacy (data stays local)
- ✅ Strands framework
- ✅ Multiple model options
- ✅ No AWS credentials needed

## Quick Start

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# Download from https://ollama.ai
```

### 2. Pull a Model

```bash
# Small, fast (recommended for learning)
ollama pull smollm:1.7b

# Larger, more capable
ollama pull llama3:8b
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment

```bash
cp .env.example .env
nano .env
```

Optional configuration:
```bash
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=smollm:1.7b
PORT=8000
```

### 6. Run Server

```bash
python app.py
```

Server starts on http://localhost:8000

## Test It

```bash
# Health check
curl http://localhost:8000/api/health

# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is Python?"}
    ]
  }'
```

## Available Models

### Small & Fast
- `smollm:1.7b` - 1.7B params, very fast
- `phi3:mini` - 3.8B params, good quality

### Medium
- `llama3:8b` - 8B params, balanced
- `mistral` - 7B params, good reasoning

### Large
- `llama3:70b` - 70B params, best quality (slow)

Change model:
```bash
# In .env
OLLAMA_MODEL=llama3:8b

# Or pull and use
ollama pull llama3:8b
```

## Cost

💰 **FREE!** (after hardware)

- No API costs
- No cloud fees
- Runs on your machine

Hardware requirements:
- 8GB RAM minimum (for smollm:1.7b)
- 16GB RAM recommended (for llama3:8b)
- GPU optional (faster with GPU)

## When to Use

✅ Learning and development
✅ Privacy-sensitive applications
✅ No internet connection
✅ Cost is a concern
✅ Small-scale applications
✅ Prototyping

## Limitations

⚠️ Slower than cloud (depends on hardware)
⚠️ Smaller models = less capable
⚠️ No native tool calling (simulated)
⚠️ Limited context window
⚠️ Requires local resources

## Troubleshooting

### "Cannot connect to Ollama"

```bash
# Make sure Ollama is running
ollama serve

# Check if model is installed
ollama list

# Pull model if needed
ollama pull smollm:1.7b
```

### "Model is too slow"

```bash
# Use smaller model
ollama pull smollm:1.7b

# Or enable GPU (automatic if available)
```

### "Out of memory"

```bash
# Use smaller model
OLLAMA_MODEL=smollm:1.7b

# Or close other applications
```

## Comparison with Bedrock

| Feature | Ollama | Bedrock |
|---------|--------|---------|
| Cost | Free | ~$0.016/100 chats |
| Setup | Install Ollama | AWS credentials |
| Speed | Depends on hardware | Fast, consistent |
| Quality | Good (smaller models) | Excellent |
| Privacy | 100% local | Cloud-based |
| Scaling | Single machine | Auto-scales |
| Best For | Dev/Learning | Production |

## See Also

- [Main README](../README.md) - Full documentation
- [Bedrock Version](../bedrock/) - Production alternative
- [Ollama Models](https://ollama.com/library) - Available models
