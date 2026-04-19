/**
 * Simple client-side tokenizer that maps words to numeric token IDs.
 * This simulates how a real tokenizer (like BPE) assigns IDs to text chunks.
 * 
 * NOTE: Real LLM tokenizers (tiktoken, sentencepiece) use subword tokenization.
 * This is a simplified word-level version for learning/visualization purposes.
 */

// Simple hash function to generate a consistent token ID for a given word
function hashToTokenId(word: string): number {
  let hash = 0;
  for (let i = 0; i < word.length; i++) {
    const char = word.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32-bit integer
  }
  // Map to a positive number in a realistic token ID range (0–50000)
  return Math.abs(hash) % 50000;
}

export interface TokenDict {
  [word: string]: number;
}

/**
 * Tokenizes input text and returns a dict mapping each token (word) to its ID.
 * Example: "hello world" → { "hello": 3217, "world": 4891 }
 */
export function tokenize(text: string): TokenDict {
  if (!text.trim()) return {};

  const words = text.trim().split(/\s+/);
  const dict: TokenDict = {};

  for (const word of words) {
    // Lowercase for consistent IDs (real tokenizers are case-sensitive, but this keeps it simple)
    const normalized = word.toLowerCase();
    dict[word] = hashToTokenId(normalized);
  }

  return dict;
}

/**
 * Returns an ordered array of [token, id] pairs preserving input order.
 * Useful for displaying tokens in sequence.
 */
export function tokenizeOrdered(text: string): [string, number][] {
  if (!text.trim()) return [];

  const words = text.trim().split(/\s+/);
  return words.map((word) => [word, hashToTokenId(word.toLowerCase())]);
}
