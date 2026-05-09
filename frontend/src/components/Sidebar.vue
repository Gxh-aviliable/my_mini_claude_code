<template>
  <div class="sidebar">
    <div class="sidebar-tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'sessions' }]"
        @click="activeTab = 'sessions'"
      >
        &#x1F4AC; Sessions
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'files' }]"
        @click="activeTab = 'files'"
      >
        &#x1F4C1; Files
      </button>
    </div>

    <div class="tab-content" v-show="activeTab === 'sessions'">
      <div class="session-actions">
        <button class="btn-new-session" @click="$emit('new-session')">+ New</button>
      </div>
      <div v-if="!sessions.length" class="empty-hint">No sessions yet</div>
      <div
        v-for="s in sessions"
        :key="s.id"
        :class="['session-item', { active: activeId === s.id }]"
        @click="$emit('select', s.id)"
      >
        <div class="session-title">{{ s.title || s.id.slice(0, 8) }}</div>
        <button class="btn-delete" @click.stop="$emit('delete', s.id)" title="Delete">&#x2715;</button>
      </div>
    </div>

    <div class="tab-content file-tab" v-show="activeTab === 'files'">
      <FileTree
        ref="fileTreeRef"
        :selected-path="selectedFilePath"
        @select="handleFileSelect"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import FileTree from './FileTree.vue'

defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' }
})
const emit = defineEmits(['select', 'delete', 'new-session', 'file-select'])

const activeTab = ref('sessions')
const selectedFilePath = ref('')
const fileTreeRef = ref(null)

function handleFileSelect(node) {
  selectedFilePath.value = node.path
  emit('file-select', node)
}
</script>

<style scoped>
.sidebar {
  width: 240px; background: #0d1117; border-right: 1px solid #222;
  display: flex; flex-direction: column; height: 100vh; flex-shrink: 0;
}
.sidebar-tabs { display: flex; border-bottom: 1px solid #222; flex-shrink: 0; }
.tab-btn {
  flex: 1; padding: 8px; background: none; border: none; color: #888;
  font-size: 11px; cursor: pointer; text-align: center;
}
.tab-btn.active { color: #54a0ff; border-bottom: 2px solid #54a0ff; background: #161b22; }
.tab-btn:hover { color: #ccc; }
.tab-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.file-tab { padding: 0; }

.session-actions { padding: 8px; }
.btn-new-session {
  width: 100%; background: #16213e; border: 1px solid #333; border-radius: 4px;
  color: #ccc; padding: 6px; font-size: 12px; cursor: pointer;
}
.btn-new-session:hover { background: #1a4a7a; }

.session-item {
  display: flex; align-items: center; padding: 8px 12px; cursor: pointer;
  border-bottom: 1px solid #111; font-size: 12px;
}
.session-item:hover { background: #161b22; }
.session-item.active { background: #0f3460; }
.session-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #ccc; }
.btn-delete { background: none; border: none; color: #555; cursor: pointer; font-size: 10px; }
.btn-delete:hover { color: #e74c3c; }
.empty-hint { padding: 12px; color: #666; font-size: 11px; text-align: center; }
</style>
