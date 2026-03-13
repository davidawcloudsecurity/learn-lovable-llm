import express from 'express';
import cors from 'cors';
import { BedrockRuntimeClient, ConverseStreamCommand } from '@aws-sdk/client-bedrock-runtime';

const app = express();
const PORT = process.env.PORT || 8000;

// Initialize Bedrock client
const bedrockClient = new BedrockRuntimeClient({ 
  region: process.env.AWS_REGION || 'us-east-1' 
});

app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'LearnLLM API' });
});

// Chat endpoint with streaming
app.post('/api/chat', async (req, res) => {
  try {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'Messages array is required' });
    }

    // Set headers for streaming
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Convert messages to Bedrock format
    const bedrockMessages = messages.map(msg => ({
      role: msg.role === 'assistant' ? 'assistant' : 'user',
      content: [{ text: msg.content }]
    }));

    // Bedrock API call
    const command = new ConverseStreamCommand({
      modelId: process.env.MODEL_ID || 'anthropic.claude-3-5-sonnet-20241022-v2:0',
      messages: bedrockMessages,
      inferenceConfig: {
        maxTokens: 2048,
        temperature: 0.7,
      }
    });

    const response = await bedrockClient.send(command);

    // Stream the response
    for await (const chunk of response.stream) {
      if (chunk.contentBlockDelta?.delta?.text) {
        res.write(`data: ${JSON.stringify({ text: chunk.contentBlockDelta.delta.text })}\n\n`);
      }
    }

    res.write('data: [DONE]\n\n');
    res.end();

  } catch (error) {
    console.error('Bedrock API error:', error);
    
    if (!res.headersSent) {
      res.status(500).json({ 
        error: 'Failed to process chat request',
        details: error.message 
      });
    } else {
      res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
      res.end();
    }
  }
});

app.listen(PORT, () => {
  console.log(`LearnLLM API server running on port ${PORT}`);
  console.log(`Model: ${process.env.MODEL_ID || 'anthropic.claude-3-5-sonnet-20241022-v2:0'}`);
});
