# LearnLLM Backend - AWS Bedrock Version

Production-ready backend using AWS Bedrock and Strands framework.

## Features

- ✅ AWS Bedrock (Amazon Nova models)
- ✅ Strands framework
- ✅ Native tool calling support
- ✅ Conversation memory (optional)
- ✅ Session persistence
- ✅ Guardrails support
- ✅ Production-ready
- ✅ Auto-scaling

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure AWS

```bash
aws configure
# Enter your AWS credentials
```

### 3. Enable Bedrock Models

1. Go to AWS Console → Bedrock → Model access
2. Request access to Amazon Nova models
3. Wait for approval (~2 minutes)

### 4. Set Environment Variables

```bash
cp .env.example .env
nano .env
```

Required:
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
MODEL_ID=amazon.nova-pro-v1:0
```

### 5. Run Server

```bash
# Basic version (no memory)
python app.py

# Advanced version (with memory)
python app_with_memory.py
```

## Cost

### Amazon Nova Pro (Recommended)
- Input: $0.80 per 1M tokens
- Output: $3.20 per 1M tokens
- ~$0.016 per 100 conversations

### Amazon Nova Micro (Cheapest)
- Input: $0.035 per 1M tokens
- Output: $0.14 per 1M tokens
- ~$0.007 per 100 conversations

## When to Use

✅ Production applications
✅ Need high reliability
✅ Complex reasoning required
✅ Want managed infrastructure
✅ Need guardrails/safety
✅ Multi-user applications

## See Also

- [Main README](../README.md) - Full documentation
- [Ollama Version](../ollama/) - Free local alternative
