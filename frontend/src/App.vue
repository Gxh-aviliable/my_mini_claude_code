<template>
  <LoginForm v-if="!auth.loggedIn" />

  <div v-else class="app-layout">
    <Sidebar
      :sessions="sessions"
      :activeId="activeSessionId"
      @select="selectSession"
      @new-session="newSession"
      @delete="deleteSession"
      @file-select="onFileSelect"
    />

    <div class="main-area">
      <!-- Topbar -->
      <div class="topbar">
        <div class="topbar-tabs">
          <button
            :class="['tab-btn', { active: mainTab === 'chat' }]"
            @click="mainTab = 'chat'"
          >
            Chat
          </button>
          <button
            :class="['tab-btn', { active: mainTab === 'files' }]"
            @click="mainTab = 'files'"
          >
            File Manager
          </button>
        </div>
        <button class="btn-logout" @click="auth.logout()">Logout</button>
      </div>

      <!-- Content -->
      <ChatPanel
        v-show="mainTab === 'chat'"
        :sessionId="activeSessionId"
        @session-created="onSessionCreated"
      />
      <FileManager
        v-show="mainTab === 'files'"
        ref="fileManagerRef"
        @refresh="loadSessions"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auth } from './stores/auth.js'
import * as api from './api/client.js'
import LoginForm from './components/LoginForm.vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import FileManager from './components/FileManager.vue'

const sessions = ref([])
const activeSessionId = ref('')
const mainTab = ref('chat')
const fileManagerRef = ref(null)

async function loadSessions() {
  try {
    const data = await api.listSessions()
    sessions.value = Array.isArray(data) ? data : data.sessions || []
  } catch { sessions.value = [] }
}

function selectSession(id) {
  activeSessionId.value = id
  mainTab.value = 'chat'
}

function newSession() {
  activeSessionId.value = ''
  mainTab.value = 'chat'
}

async function onSessionCreated(sid) {
  activeSessionId.value = sid
  await loadSessions()
}

function onFileSelect(node) {
  mainTab.value = 'files'
}

async function deleteSession(id) {
  try {
    await api.deleteSession(id)
    if (activeSessionId.value === id) activeSessionId.value = ''
    await loadSessions()
  } catch {}
}

onMounted(() => {
  if (auth.loggedIn) loadSessions()
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; }

.app-layout { display: flex; height: 100vh; }
.main-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 16px; background: #16213e; border-bottom: 1px solid #222; flex-shrink: 0;
}
.topbar-tabs { display: flex; }
.tab-btn {
  padding: 10px 16px; background: none; border: none; color: #888;
  font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent;
}
.tab-btn.active { color: #54a0ff; border-bottom-color: #54a0ff; }
.tab-btn:hover { color: #ccc; }

.btn-logout {
  background: transparent; border: 1px solid #444; color: #999;
  padding: 4px 14px; border-radius: 4px; cursor: pointer; font-size: 12px;
}
.btn-logout:hover { color: #e74c3c; border-color: #e74c3c; }
</style>
