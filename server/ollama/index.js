import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';

const app = express();
const PORT = process.env.PORT || 8000;
const OLLAMA_URL = process.env.OLLAMA_URL || 'http://localhost:11434';
const MODEL = process.env.OLLAMA_MODEL || 'smollm:1.7b';

// Create logs directory
const logsDir = path.join(process.cwd(), 'logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

// Logger function
function log(message, data = null) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    message,
    ...(data && { data })
  };
  
  // Console output
  console.log(`[${timestamp}] ${message}`);
  if (data) {
    console.log(JSON.stringify(data, null, 2));
  }
  
  // File output
  const logFile = path.join(logsDir, `chat-${new Date().toISOString().split('T')[0]}.log`);
  fs.appendFileSync(logFile, JSON.stringify(logEntry) + '\n');
}

app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'LearnLLM API (Ollama)' });
});

// Logs endpoint - view recent logs
app.get('/api/logs', (req, res) => {
  try {
    const today = new Date().toISOString().split('T')[0];
    const logFile = path.join(logsDir, `chat-${today}.log`);
    
    if (!fs.existsSync(logFile)) {
      return res.json({ logs: [], message: 'No logs for today' });
    }
    
    const logs = fs.readFileSync(logFile, 'utf-8')
      .split('\n')
      .filter(line => line.trim())
      .map(line => JSON.parse(line))
      .slice(-50); // Last 50 entries
    
    res.json({ logs, count: logs.length });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Chat endpoint with streaming
app.post('/api/chat', async (req, res) => {
  const requestId = Date.now();
  
  try {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'Messages array is required' });
    }

    // Log incoming request
    log(`[${requestId}] Incoming chat request`, {
      messageCount: messages.length,
      messages: messages
    });

    // Set headers for streaming
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const requestBody = {
      model: MODEL,
      messages: messages,
      stream: true,
    };

    log(`[${requestId}] Sending to Ollama`, {
      url: `${OLLAMA_URL}/api/chat`,
      model: MODEL,
      messageCount: messages.length
    });

    // Call Ollama API
    const response = await fetch(`${OLLAMA_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      throw new Error(`Ollama API error: ${response.status}`);
    }

    let fullResponse = '';
    let chunkCount = 0;
    const chunks = [];

    // Stream the response
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(line => line.trim());

      for (const line of lines) {
        try {
          const parsed = JSON.parse(line);
          chunkCount++;
          chunks.push(parsed);
          
          if (parsed.message?.content) {
            fullResponse += parsed.message.content;
            res.write(`data: ${JSON.stringify({ text: parsed.message.content })}\n\n`);
          }
          
          if (parsed.done) {
            // Log complete response with metadata
            log(`[${requestId}] Response complete`, {
              fullResponse,
              chunkCount,
              responseLength: fullResponse.length,
              duration: parsed.total_duration ? (parsed.total_duration / 1e9).toFixed(2) + 's' : 'N/A',
              tokensGenerated: parsed.eval_count || 'N/A',
              promptTokens: parsed.prompt_eval_count || 'N/A',
              model: parsed.model || MODEL,
              metadata: {
                total_duration: parsed.total_duration,
                load_duration: parsed.load_duration,
                prompt_eval_count: parsed.prompt_eval_count,
                prompt_eval_duration: parsed.prompt_eval_duration,
                eval_count: parsed.eval_count,
                eval_duration: parsed.eval_duration
              }
            });
            
            res.write('data: [DONE]\n\n');
            res.end();
            return;
          }
        } catch (e) {
          log(`[${requestId}] Failed to parse chunk`, { error: e.message, line });
        }
      }
    }

    res.write('data: [DONE]\n\n');
    res.end();

  } catch (error) {
    log(`[${requestId}] Error occurred`, {
      error: error.message,
      stack: error.stack
    });
    
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
  log('Server started', {
    port: PORT,
    ollamaUrl: OLLAMA_URL,
    model: MODEL,
    logsDirectory: logsDir
  });
});
