<template>
  <div class="chat-panel">
    <div class="chat-header">
      <span class="session-label">{{ activeId ? 'Session: ' + activeId.slice(0, 8) : 'New Session' }}</span>
      <span v-if="streaming" class="badge streaming-badge">Generating...</span>
      <span v-if="currentTool" class="badge tool-badge">Tool: {{ currentTool }}</span>
      <span v-if="pendingConfirm" class="badge confirm-badge">Awaiting Confirmation</span>
    </div>

    <div class="messages" ref="msgContainer">
      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <div class="msg-role">{{ msg.role === 'user' ? 'You' : 'Agent' }}</div>
        <div class="msg-content">
          <pre :class="['msg-text', msg.streaming ? 'streaming' : '']">{{ msg.content }}</pre>
        </div>
      </div>

      <div v-if="messages.length === 0 && !streaming" class="empty-chat">
        Start a conversation by sending a message below.
      </div>
    </div>

    <!-- Tool Confirmation Dialog -->
    <div v-if="pendingConfirm" class="confirm-overlay">
      <div class="confirm-dialog">
        <h3>Tool Execution Confirmation</h3>
        <p class="confirm-message">{{ pendingConfirm.message }}</p>
        <ul class="confirm-tools">
          <li v-for="(tool, idx) in pendingConfirm.tools" :key="tool.id || idx" class="confirm-tool-item">
            <input type="checkbox" v-model="tool.approved" :id="'tool-' + idx" />
            <label :for="'tool-' + idx">
              <strong>{{ tool.name }}</strong>
              <span class="tool-desc">{{ tool.description }}</span>
            </label>
          </li>
        </ul>
        <div class="confirm-actions">
          <button @click="approveTools" class="btn-approve">Approve Selected</button>
          <button @click="approveAll" class="btn-approve-all">Approve All</button>
          <button @click="rejectTools" class="btn-reject">Reject All</button>
        </div>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="input"
        @keydown.enter.exact="send"
        placeholder="Type your message... (Enter to send)"
        :disabled="streaming || pendingConfirm"
        rows="2"
      ></textarea>
      <button @click="send" :disabled="streaming || pendingConfirm || !input.trim()" class="btn-send">
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
const streaming = ref(false)
const currentTool = ref('')
const msgContainer = ref(null)
const activeId = ref(props.sessionId)
const pendingConfirm = ref(null)
const streamMsgRef = ref(null)

function scrollBottom() {
  nextTick(() => {
    const el = msgContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send() {
  const content = input.value.trim()
  if (!content || streaming.value || pendingConfirm.value) return
  input.value = ''

  messages.value.push({ role: 'user', content })
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
      return
    }
  }

  // Create streaming message placeholder
  const streamMsg = { role: 'assistant', content: '', streaming: true }
  messages.value.push(streamMsg)
  streamMsgRef.value = streamMsg
  streaming.value = true
  scrollBottom()

  startStream(sid, content, isNewSession)
}

function startStream(sessionId, content, isNewSession) {
  api.streamMessage({
    session_id: sessionId,
    content,
    onDelta: (delta) => {
      if (streamMsgRef.value) {
        streamMsgRef.value.content += delta
        scrollBottom()
      }
    },
    onToolStart: (name) => {
      currentTool.value = name
      if (streamMsgRef.value) {
        streamMsgRef.value.content += `\n[Running: ${name}]\n`
        scrollBottom()
      }
    },
    onToolEnd: (name) => {
      currentTool.value = ''
    },
    onInterrupt: (data) => {
      // Show confirmation dialog
      console.log('[ChatPanel] Interrupt received:', data)
      const tools = (data.tools || []).map(t => ({ ...t, approved: true }))
      pendingConfirm.value = {
        session_id: sessionId,
        message: data.message || 'Confirm tool execution?',
        tools,
        isNewSession
      }
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) {
        streamMsgRef.value.content += '\n⏳ Waiting for your confirmation...\n'
        scrollBottom()
      }
    },
    onError: (err) => {
      if (streamMsgRef.value) {
        streamMsgRef.value.content += `\n❌ Error: ${err}`
      }
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) streamMsgRef.value.streaming = false
    },
    onDone: () => {
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) streamMsgRef.value.streaming = false
      if (isNewSession && !pendingConfirm.value) {
        emit('session-created', sessionId)
      }
      scrollBottom()
    }
  })
}

function approveTools() {
  if (!pendingConfirm.value) return

  const approvedIds = pendingConfirm.value.tools.filter(t => t.approved).map(t => t.id)
  resumeAfterConfirm(approvedIds)
}

function approveAll() {
  if (!pendingConfirm.value) return

  const allIds = pendingConfirm.value.tools.map(t => t.id)
  resumeAfterConfirm(allIds)
}

function rejectTools() {
  if (!pendingConfirm.value) return

  if (streamMsgRef.value) {
    streamMsgRef.value.content += '\n❌ Tool execution rejected by user\n'
    scrollBottom()
  }

  if (pendingConfirm.value.isNewSession) {
    emit('session-created', pendingConfirm.value.session_id)
  }

  pendingConfirm.value = null
  streamMsgRef.value = null
}

function resumeAfterConfirm(approvedIds) {
  if (!pendingConfirm.value) return

  const sessionId = pendingConfirm.value.session_id
  const isNewSession = pendingConfirm.value.isNewSession

  pendingConfirm.value = null
  streaming.value = true
  currentTool.value = ''

  if (streamMsgRef.value) {
    streamMsgRef.value.content += `\n✅ Proceeding with ${approvedIds.length} approved tool(s)\n`
    streamMsgRef.value.streaming = true
    scrollBottom()
  }

  api.resumeStream({
    session_id: sessionId,
    approved: true,
    approved_ids: approvedIds,
    onDelta: (delta) => {
      if (streamMsgRef.value) {
        streamMsgRef.value.content += delta
        scrollBottom()
      }
    },
    onToolStart: (name) => {
      currentTool.value = name
      if (streamMsgRef.value) {
        streamMsgRef.value.content += `\n[Running: ${name}]\n`
        scrollBottom()
      }
    },
    onToolEnd: (name) => {
      currentTool.value = ''
    },
    onInterrupt: (data) => {
      // Another interrupt
      const tools = (data.tools || []).map(t => ({ ...t, approved: true }))
      pendingConfirm.value = {
        session_id: sessionId,
        message: data.message || 'Confirm tool execution?',
        tools,
        isNewSession
      }
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) {
        streamMsgRef.value.content += '\n⏳ Waiting for your confirmation...\n'
        streamMsgRef.value.streaming = false
        scrollBottom()
      }
    },
    onError: (err) => {
      if (streamMsgRef.value) {
        streamMsgRef.value.content += `\n❌ Error: ${err}`
      }
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) streamMsgRef.value.streaming = false
    },
    onDone: () => {
      streaming.value = false
      currentTool.value = ''
      if (streamMsgRef.value) streamMsgRef.value.streaming = false
      if (isNewSession) {
        emit('session-created', sessionId)
      }
      scrollBottom()
    }
  })
}

watch(() => props.sessionId, (newId) => {
  if (newId !== activeId.value) {
    activeId.value = newId
    messages.value = []
    streaming.value = false
    currentTool.value = ''
    pendingConfirm.value = null
    streamMsgRef.value = null
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
.badge { font-size: 11px; animation: pulse 1s infinite; }
.streaming-badge { color: #f39c12; }
.tool-badge { color: #3498db; background: #1a3a5c; padding: 2px 8px; border-radius: 4px; }
.confirm-badge { color: #e74c3c; background: #2c3e50; padding: 2px 8px; border-radius: 4px; }
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
.msg-text.streaming {
  color: #f39c12;
}
.msg-text.streaming::after {
  content: '▊';
  animation: blink 0.5s infinite;
  margin-left: 2px;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* Confirmation Dialog */
.confirm-overlay {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.confirm-dialog {
  background: #1a1a2e; border: 1px solid #3498db; border-radius: 12px;
  padding: 20px; max-width: 400px; width: 90%; color: #e0e0e0;
}
.confirm-dialog h3 { color: #3498db; margin: 0 0 10px 0; font-size: 16px; }
.confirm-message { color: #888; font-size: 13px; margin-bottom: 15px; }
.confirm-tools { list-style: none; padding: 0; margin: 0 0 15px 0; }
.confirm-tool-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px; background: #16213e; border-radius: 6px; margin-bottom: 8px;
}
.confirm-tool-item input[type="checkbox"] { margin-top: 3px; }
.confirm-tool-item label { flex: 1; }
.confirm-tool-item strong { color: #3498db; }
.tool-desc { color: #888; font-size: 12px; display: block; margin-top: 4px; }

.confirm-actions { display: flex; gap: 10px; justify-content: flex-end; }
.btn-approve {
  padding: 8px 16px; background: #27ae60; border: none; border-radius: 6px;
  color: #fff; font-size: 13px; cursor: pointer;
}
.btn-approve:hover { background: #2ecc71; }
.btn-approve-all {
  padding: 8px 16px; background: #3498db; border: none; border-radius: 6px;
  color: #fff; font-size: 13px; cursor: pointer;
}
.btn-approve-all:hover { background: #2980b9; }
.btn-reject {
  padding: 8px 16px; background: #e74c3c; border: none; border-radius: 6px;
  color: #fff; font-size: 13px; cursor: pointer;
}
.btn-reject:hover { background: #c0392b; }

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