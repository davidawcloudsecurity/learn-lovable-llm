type Message = { role: "user" | "assistant"; content: string };

// Track session ID across requests
let currentSessionId: string | null = null;

export function resetSession() {
  currentSessionId = null;
}

export interface TokenUsage {
  input_tokens: number | null;
  output_tokens: number | null;
}

export async function streamChatResponse(
  messages: Message[],
  onDelta: (text: string) => void,
  onDone: (tokenUsage: TokenUsage) => void,
  onError: (error: string) => void
) {
  try {
    // Get the latest user message
    const lastUserMessage = [...messages].reverse().find(m => m.role === "user");
    if (!lastUserMessage) {
      onError("No user message found");
      return;
    }

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: lastUserMessage.content,
        session_id: currentSessionId,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Store session ID for subsequent requests
    if (data.session_id) {
      currentSessionId = data.session_id;
    }

    // Get the last bot message from the response
    const botMessages = data.messages?.filter((m: any) => m.message_type === "BOT");
    const lastBotMessage = botMessages?.[botMessages.length - 1];

    if (lastBotMessage?.message) {
      onDelta(lastBotMessage.message);
    }

    onDone({
      input_tokens: data.input_tokens ?? null,
      output_tokens: data.output_tokens ?? null,
    });
  } catch (error) {
    console.error('Chat API error:', error);
    onError(error instanceof Error ? error.message : 'Unknown error');
  }
}
