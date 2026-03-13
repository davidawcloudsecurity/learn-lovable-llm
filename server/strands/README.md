# LearnLLM Backend - Strands Framework

Python backend with two options: AWS Bedrock (production) or Ollama (local/free).

## Choose Your Backend

This directory contains two implementations:

### 📁 [bedrock/](bedrock/) - AWS Bedrock (Production)
- Cloud-based (AWS)
- Production-ready
- $0.016 per 100 conversations
- Best quality
- Auto-scaling

### 📁 [ollama/](ollama/) - Ollama (Local)
- Runs locally
- Free (no API costs)
- Privacy-first
- Good for development
- No AWS needed

## Quick Decision

- **Learning?** → Use [Ollama](ollama/)
- **Production?** → Use [Bedrock](bedrock/)
- **Not sure?** → Read [COMPARISON.md](COMPARISON.md)

## Quick Setup

```bash
# Run the setup script
bash setup.sh

# Or manually:
cd bedrock  # or cd ollama
pip install -r requirements.txt
python app.py
```

## Why Strands?

| Feature | Node.js/Ollama | Python/Strands |
|---------|----------------|----------------|
| Model | Local (smollm:1.7b) | Cloud (Amazon Nova Pro) |
| Cost | Free (hardware) | Pay per token (~$0.80/1M) |
| Performance | Depends on hardware | Consistent, fast |
| Reliability | Variable | Production-ready |
| Tool Calling | Manual | Native support |
| Memory | Manual | Built-in |
| Guardrails | None | AWS Bedrock Guardrails |
| Scaling | Single machine | Auto-scales |

## Two Versions

### 1. Basic Version (`app.py`)
- Simple chat endpoint
- No conversation memory
- Stateless
- Good for: Simple Q&A, testing

### 2. Advanced Version (`app_with_memory.py`)
- Conversation memory (sliding window)
- Session persistence
- Multi-user support
- Good for: Production, multi-turn conversations

## Prerequisites

### 1. AWS Account Setup

```bash
# Install AWS CLI
pip install awscli

# Configure credentials
aws configure
# Enter:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region: us-east-1
# - Default output format: json
```

### 2. Enable Bedrock Models

1. Go to AWS Console → Bedrock → Model access
2. Request access to:
   - Amazon Nova Micro (cheapest)
   - Amazon Nova Lite (balanced)
   - Amazon Nova Pro (most capable)
3. Wait for approval (~2 minutes)

### 3. Install Python Dependencies

```bash
cd learn-lovable-llm/server/strands
pip install -r requirements.txt
```

## Quick Start

### Step 1: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your AWS credentials
nano .env
```

Required variables:
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
MODEL_ID=amazon.nova-pro-v1:0
```

### Step 2: Test AWS Connection

```python
# test_aws.py
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
response = bedrock.invoke_model(
    modelId='amazon.nova-micro-v1:0',
    body='{"messages":[{"role":"user","content":[{"text":"Hello"}]}]}'
)
print("✅ AWS Bedrock connection successful!")
```

### Step 3: Run Basic Server

```bash
python app.py
```

Server starts on http://localhost:8000

### Step 4: Test Endpoint

```bash
# Health check
curl http://localhost:8000/api/health

# Chat request
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is Python?"}
    ]
  }'
```

## Using the Advanced Version (with Memory)

### Start Server

```bash
python app_with_memory.py
```

### Create Session

```bash
curl -X POST http://localhost:8000/api/session/new
# Returns: {"session_id": "session-1234567890"}
```

### Chat with Memory

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "My name is Alice"}
    ],
    "session_id": "session-1234567890"
  }'

# Later in same session...
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is my name?"}
    ],
    "session_id": "session-1234567890"
  }'
# Agent remembers: "Your name is Alice"
```

### List Sessions

```bash
curl http://localhost:8000/api/sessions
```

### Delete Session

```bash
curl -X DELETE http://localhost:8000/api/session/session-1234567890
```

## Frontend Integration

Your existing frontend (`src/lib/chat-api.ts`) works without changes! Just point it to the Python backend:

### Option 1: Update Vite Proxy (Development)

```javascript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // Python backend
        changeOrigin: true
      }
    }
  }
})
```

### Option 2: Update Nginx (Production)

```nginx
# /etc/nginx/sites-available/app
location /api/ {
    proxy_pass http://localhost:8000;  # Python backend
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
}
```

## API Endpoints

### Basic Version (`app.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/chat` | POST | Chat with streaming |
| `/api/logs` | GET | View recent logs |
| `/api/model-info` | GET | Model information |

### Advanced Version (`app_with_memory.py`)

All basic endpoints plus:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session/new` | POST | Create new session |
| `/api/session/<id>` | DELETE | Delete session |
| `/api/sessions` | GET | List all sessions |

## Configuration Options

### Model Selection

```bash
# Cheapest (good for testing)
MODEL_ID=amazon.nova-micro-v1:0

# Balanced (recommended)
MODEL_ID=amazon.nova-lite-v1:0

# Most capable (best quality)
MODEL_ID=amazon.nova-pro-v1:0
```

### Conversation Window

```bash
# Number of messages to remember
CONVERSATION_WINDOW=10  # Default
CONVERSATION_WINDOW=20  # More context
CONVERSATION_WINDOW=5   # Less context (cheaper)
```

### Logging

```bash
LOG_LEVEL=INFO     # Standard
LOG_LEVEL=DEBUG    # Verbose
LOG_LEVEL=WARNING  # Minimal
```

## Adding Guardrails (Safety)

### Step 1: Create Guardrail in AWS Console

1. Go to Bedrock → Guardrails
2. Create guardrail
3. Add filters:
   - Content filters (hate, violence, sexual)
   - Topic filters (medical advice, legal advice)
   - PII filters (SSN, credit cards)
4. Note the Guardrail ID

### Step 2: Configure in .env

```bash
GUARDRAIL_ID=your-guardrail-id
GUARDRAIL_VERSION=DRAFT
```

### Step 3: Restart Server

```bash
python app.py
```

Now all responses are filtered through guardrails!

## Cost Estimation

### Amazon Nova Pro (Recommended)

- Input: $0.80 per 1M tokens
- Output: $3.20 per 1M tokens

Example costs:
- 100 conversations (avg 500 tokens each): ~$0.16
- 1,000 conversations: ~$1.60
- 10,000 conversations: ~$16.00

### Amazon Nova Micro (Cheapest)

- Input: $0.035 per 1M tokens
- Output: $0.14 per 1M tokens

Example costs:
- 100 conversations: ~$0.007
- 1,000 conversations: ~$0.07
- 10,000 conversations: ~$0.70

## Deployment

### Option 1: Same EC2 as Frontend

```bash
# SSH to EC2
ssh ec2-user@your-instance

# Install Python
sudo yum install python3 python3-pip -y

# Clone repo
cd /opt/app
git pull

# Install dependencies
cd server/strands
pip3 install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add AWS credentials

# Run with PM2
pm2 start app.py --name learnllm-backend --interpreter python3
pm2 save
```

### Option 2: Separate EC2 for Backend

Update Terraform to use Python backend:

```hcl
# main.tf
user_data = <<-EOF
  #!/bin/bash
  yum install -y python3 python3-pip git
  cd /opt
  git clone https://github.com/your-repo/learn-lovable-llm.git app
  cd app/server/strands
  pip3 install -r requirements.txt
  
  # Create systemd service
  cat > /etc/systemd/system/learnllm.service <<'SERVICE'
  [Unit]
  Description=LearnLLM Backend
  After=network.target
  
  [Service]
  Type=simple
  User=ec2-user
  WorkingDirectory=/opt/app/server/strands
  Environment="PATH=/usr/local/bin:/usr/bin"
  ExecStart=/usr/bin/python3 app.py
  Restart=always
  
  [Install]
  WantedBy=multi-user.target
  SERVICE
  
  systemctl enable learnllm
  systemctl start learnllm
EOF
```

### Option 3: AWS Lambda (Serverless)

```python
# lambda_handler.py
from app import app
from mangum import Mangum

handler = Mangum(app)
```

Deploy with AWS SAM or Serverless Framework.

## Monitoring

### CloudWatch Logs

```python
# Add CloudWatch handler
import watchtower

logger.addHandler(watchtower.CloudWatchLogHandler(
    log_group='/aws/learnllm/backend',
    stream_name='chat-api'
))
```

### Metrics

```python
# Add custom metrics
import boto3

cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='LearnLLM',
    MetricData=[{
        'MetricName': 'ChatRequests',
        'Value': 1,
        'Unit': 'Count'
    }]
)
```

## Troubleshooting

### "No module named 'strands'"

```bash
pip install strands-agents
```

### "Unable to locate credentials"

```bash
# Check AWS credentials
aws sts get-caller-identity

# If fails, reconfigure
aws configure
```

### "Model access denied"

1. Go to AWS Console → Bedrock → Model access
2. Request access to the model
3. Wait for approval

### "Rate limit exceeded"

You're making too many requests. Solutions:
- Add rate limiting
- Use smaller model
- Implement caching

### Slow responses

- Use `amazon.nova-micro-v1:0` (faster, cheaper)
- Reduce `max_tokens` in model config
- Add caching for common queries

## Migration Checklist

- [ ] AWS account configured
- [ ] Bedrock model access enabled
- [ ] Python dependencies installed
- [ ] Environment variables configured
- [ ] Basic server tested locally
- [ ] Frontend proxy updated
- [ ] Logs working
- [ ] Deployed to EC2
- [ ] Nginx configured
- [ ] SSL certificate (if needed)
- [ ] Monitoring setup
- [ ] Cost alerts configured

## Next Steps

1. **Add Tools**: Give agent access to APIs, databases
2. **Add Guardrails**: Implement safety filters
3. **Add Caching**: Cache common responses
4. **Add Rate Limiting**: Prevent abuse
5. **Add Authentication**: Secure your API
6. **Add Analytics**: Track usage patterns

## Resources

- [Strands Documentation](https://strandsagents.com/latest/)
- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- [Flask Documentation](https://flask.palletsprojects.com/)

## Support

Issues? Questions?
- Check logs: `tail -f logs/chat-*.log`
- Test AWS: `aws bedrock-runtime list-foundation-models`
- Review code: Both `app.py` files have detailed comments

---

**You're now running a production-ready AI backend with AWS Bedrock and Strands! 🚀**
