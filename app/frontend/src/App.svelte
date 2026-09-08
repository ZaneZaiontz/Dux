<script lang="ts">
  import { streamReply } from "./services/chat";
  import type { Message } from "./types";

  const conversationId = crypto.randomUUID();

  let messages = $state<Message[]>([]);
  let draft = $state("");
  let step = $state("");
  let busy = $state(false);

  async function send() {
    if (!draft.trim() || busy) return;

    const text = draft;
    draft = "";
    busy = true;

    messages.push({ role: "you", text });
    messages.push({ role: "dux", text: "" });
    const reply = messages[messages.length - 1];

    try {
      await streamReply(text, conversationId, (event) => {
        if (event.type === "token") {
          step = "";
          reply.text += event.text;
        } else {
          step = event.node;
        }
      });
    } catch (error) {
      reply.text = `Something went wrong: ${error}`;
    }

    busy = false;
    step = "";
  }
</script>

<main>
  <h1>Dux</h1>

  <div class="thread">
    <ul class="messages">
      {#each messages as message}
        <li class={message.role}>
          <span class="who">{message.role}</span>
          <p>{message.text}</p>
        </li>
      {/each}
    </ul>

    {#if step}
      <p class="step">... {step}</p>
    {/if}
  </div>

  <form onsubmit={(event) => { event.preventDefault(); send(); }}>
    <input
      bind:value={draft}
      placeholder="What are you stuck on?"
      disabled={busy}
    />
    <button type="submit" disabled={busy}>Send</button>
  </form>
</main>
