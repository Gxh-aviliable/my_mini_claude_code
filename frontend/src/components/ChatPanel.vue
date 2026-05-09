<template>
  <div class="chat-panel">
    <div class="chat-header">
      <span class="session-label">{{ activeId ? 'Session: ' + activeId.slice(0, 8) : 'New Session' }}</span>
      <span v-if="loading" class="badge">Thinking...</span>
    </div>

    <div class="messages" ref="msgContainer">
      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <div class="msg-role">{{ msg.role === 'user' ? 'You' : 'Agent' }}</div>
        <div class="msg-content">
          <pre class="msg-text">{{ msg.content }}</pre>
        </div>
      </div>

      <div v-if="loading" class="msg assistant">
        <div class="msg-role">Agent</div>
        <div class="msg-content">
          <pre class="msg-text thinking">Thinking...<span class="cursor">|</span></pre>
        </div>
      </div>

      <div v-if="messages.length === 0 && !loading" class="empty-chat">
        Start a conversation by sending a message below.
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="input"
        @keydown.enter.exact="send"
        placeholder="Type your message... (Enter to send)"
        :disabled="loading"
        rows="2"
      ></textarea>
      <button @click="send" :disabled="loading || !input.trim()" class="btn-send">
        Send
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import * as api from '../api/client.js'

const props = defineProps({
  sessionId: { type: String, default: '' }
})
const emit = defineEmits(['session-created'])

const input = ref('')
const messages = ref([])
const loading = ref(false)
const msgContainer = ref(null)
const activeId = ref(props.sessionId)

function scrollBottom() {
  nextTick(() => {
    const el = msgContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send() {
  const content = input.value.trim()
  if (!content || loading.value) return
  input.value = ''

  messages.value.push({ role: 'user', content })
  loading.value = true
  scrollBottom()

  // Create session if needed
  let sid = activeId.value
  const isNewSession = !sid
  if (isNewSession) {
    try {
      const session = await api.createSession()
      sid = session.id
      activeId.value = sid
    } catch (e) {
      messages.value.push({ role: 'assistant', content: 'Failed to create session: ' + e.message })
      loading.value = false
      return
    }
  }

  try {
    const data = await api.sendMessage({ session_id: sid, content })
    messages.value.push({ role: data.role || 'assistant', content: data.content })
    // Only emit AFTER response arrives, so parent doesn't destroy us
    if (isNewSession) {
      emit('session-created', sid)
    }
  } catch (e) {
    messages.value.push({ role: 'assistant', content: 'Error: ' + e.message })
  } finally {
    loading.value = false
    scrollBottom()
  }
}

watch(() => props.sessionId, (newId) => {
  if (newId !== activeId.value) {
    activeId.value = newId
    messages.value = []
  }
})
</script>

<style scoped>
.chat-panel {
  flex: 1; display: flex; flex-direction: column; background: #1a1a2e;
}
.chat-header {
  padding: 12px 16px; border-bottom: 1px solid #222;
  display: flex; align-items: center; gap: 10px;
}
.session-label { color: #888; font-size: 12px; }
.badge { color: #f39c12; font-size: 11px; animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.messages {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
}
.msg { max-width: 80%; }
.msg.user { align-self: flex-end; }
.msg.assistant { align-self: flex-start; }
.msg-role { font-size: 11px; color: #666; margin-bottom: 2px; }
.msg.user .msg-role { text-align: right; }
.msg-content { border-radius: 8px; padding: 10px 14px; }
.msg.user .msg-content { background: #0f3460; color: #e0e0e0; }
.msg.assistant .msg-content { background: #16213e; color: #ddd; border: 1px solid #222; }

.msg-text {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; font-size: 13px; line-height: 1.5;
}
.msg-text.thinking { color: #888; }
.cursor { animation: blink 1s infinite; color: #f39c12; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

.input-area {
  display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #222;
}
.input-area textarea {
  flex: 1; background: #16213e; border: 1px solid #333; border-radius: 6px;
  color: #e0e0e0; padding: 10px; font-size: 14px; outline: none; resize: none;
  font-family: inherit;
}
.input-area textarea:focus { border-color: #0f3460; }
.btn-send {
  padding: 0 20px; background: #0f3460; border: none; border-radius: 6px;
  color: #e0e0e0; font-size: 14px; cursor: pointer; white-space: nowrap;
}
.btn-send:hover:not(:disabled) { background: #1a4a7a; }
.btn-send:disabled { opacity: 0.5; cursor: not-allowed; }
.empty-chat { color: #555; font-size: 13px; text-align: center; padding: 40px; }
</style>
