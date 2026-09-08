import type { StreamEvent } from "../types";

export const SERVER_URL =
  import.meta.env.VITE_SERVER_URL ?? "http://localhost:8000";

const DATA_PREFIX = "data: ";

/**
 * Send one message to Dux and report each event as it arrives.
 *
 * The reply is a server sent event stream, so `onEvent` fires while Dux is
 * still working rather than once at the end.
 *
 * @param userInput what the developer typed
 * @param conversationId the thread this message belongs to
 * @param onEvent called for every event as it arrives
 */
export async function streamReply(
  userInput: string,
  conversationId: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${SERVER_URL}/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_input: userInput,
      conversation_id: conversationId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Dux answered with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Dux answered with no body to read");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith(DATA_PREFIX)) {
        onEvent(JSON.parse(line.slice(DATA_PREFIX.length)) as StreamEvent);
      }
    }
  }
}
