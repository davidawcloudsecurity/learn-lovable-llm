const responses = [
  "That's a great question! DeepSeek is designed to provide thoughtful, helpful responses across a wide range of topics. How can I help you further?",
  "I'd be happy to help with that. Let me break it down:\n\n1. **First**, consider the core problem you're trying to solve\n2. **Second**, evaluate the available options\n3. **Third**, choose the approach that best fits your needs\n\nWould you like me to elaborate on any of these points?",
  "Here's what I think about that:\n\n> The best way to predict the future is to create it.\n\nLet me know if you'd like to explore this topic further!",
  "That's an interesting perspective. Based on my understanding:\n\n- The key factor here is **context**\n- Different situations call for different approaches\n- There's rarely a one-size-fits-all solution\n\nWhat specific aspect would you like to dive deeper into?",
  "I can help with that! Here's a quick overview:\n\n```\nStep 1: Define your goal\nStep 2: Gather information\nStep 3: Take action\nStep 4: Review and iterate\n```\n\nShall I go into more detail on any step?",
];

export function getMockResponse(): string {
  return responses[Math.floor(Math.random() * responses.length)];
}

export async function streamMockResponse(
  onDelta: (text: string) => void,
  onDone: () => void
) {
  const response = getMockResponse();
  const words = response.split(" ");

  for (let i = 0; i < words.length; i++) {
    await new Promise((r) => setTimeout(r, 30 + Math.random() * 50));
    onDelta((i === 0 ? "" : " ") + words[i]);
  }

  onDone();
}
