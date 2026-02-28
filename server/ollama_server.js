import express from 'express';
import cors from 'cors';

const app = express();
const PORT = process.env.PORT || 8000;
const OLLAMA_URL = process.env.OLLAMA_URL || 'http://localhost:11434';
const MODEL = process.env.OLLAMA_MODEL || 'llama3.2';

app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'LearnLLM API (Ollama)' });
});

// Chat endpoint with streaming
app.post('/api/chat', async (req, res) => {
  try {
    const { messages } = req.body;

    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'Messages array is required' });
    }

    // Log incoming request
    console.log('\n=== INCOMING REQUEST ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('Messages:', JSON.stringify(messages, null, 2));
    console.log('Message count:', messages.length);

    // Set headers for streaming
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const requestBody = {
      model: MODEL,
      messages: messages,
      stream: true,
    };

    console.log('\n=== OLLAMA REQUEST ===');
    console.log('URL:', `${OLLAMA_URL}/api/chat`);
    console.log('Body:', JSON.stringify(requestBody, null, 2));

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

    console.log('\n=== OLLAMA RESPONSE STREAM ===');
    let fullResponse = '';
    let chunkCount = 0;

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
          
          // Log full chunk details
          console.log(`\nChunk #${chunkCount}:`, JSON.stringify(parsed, null, 2));
          
          if (parsed.message?.content) {
            fullResponse += parsed.message.content;
            res.write(`data: ${JSON.stringify({ text: parsed.message.content })}\n\n`);
          }
          
          if (parsed.done) {
            console.log('\n=== RESPONSE COMPLETE ===');
            console.log('Full response:', fullResponse);
            console.log('Total chunks:', chunkCount);
            console.log('Response length:', fullResponse.length);
            
            // Log metadata if available
            if (parsed.total_duration) {
              console.log('Duration:', parsed.total_duration / 1e9, 'seconds');
            }
            if (parsed.eval_count) {
              console.log('Tokens generated:', parsed.eval_count);
            }
            if (parsed.prompt_eval_count) {
              console.log('Prompt tokens:', parsed.prompt_eval_count);
            }
            
            res.write('data: [DONE]\n\n');
            res.end();
            return;
          }
        } catch (e) {
          console.error('Failed to parse chunk:', line, e);
        }
      }
    }

    res.write('data: [DONE]\n\n');
    res.end();

  } catch (error) {
    console.error('\n=== ERROR ===');
    console.error('Error details:', error);
    console.error('Stack:', error.stack);
    
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
  console.log(`Ollama URL: ${OLLAMA_URL}`);
  console.log(`Model: ${MODEL}`);
});
