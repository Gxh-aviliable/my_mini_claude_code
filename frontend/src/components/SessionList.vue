<template>
  <div class="session-panel">
    <div class="panel-header">
      <span>Sessions</span>
      <button class="btn-new" @click="$emit('new-session')" title="New session">+</button>
    </div>
    <div class="session-list">
      <div
        v-for="s in sessions"
        :key="s.id"
        :class="['session-item', { active: s.id === activeId }]"
        @click="$emit('select', s.id)"
      >
        <span class="session-title">{{ s.title || s.id?.slice(0, 8) }}</span>
        <button class="btn-del" @click.stop="$emit('delete', s.id)">x</button>
      </div>
      <p v-if="sessions.length === 0" class="empty">No sessions yet</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' }
})
defineEmits(['select', 'new-session', 'delete'])
</script>

<style scoped>
.session-panel {
  width: 220px; min-width: 220px; background: #16213e;
  display: flex; flex-direction: column; border-right: 1px solid #222;
}
.panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; border-bottom: 1px solid #222; color: #ccc; font-size: 13px;
}
.btn-new {
  background: #0f3460; border: none; color: #fff;
  width: 24px; height: 24px; border-radius: 4px; cursor: pointer; font-size: 16px;
}
.session-list { flex: 1; overflow-y: auto; padding: 8px; }
.session-item {
  padding: 10px 12px; border-radius: 6px; cursor: pointer; color: #aaa;
  font-size: 13px; display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 2px;
}
.session-item:hover { background: #1a2744; }
.session-item.active { background: #0f3460; color: #e0e0e0; }
.session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.btn-del { background: none; border: none; color: #666; cursor: pointer; font-size: 12px; visibility: hidden; }
.session-item:hover .btn-del { visibility: visible; }
.btn-del:hover { color: #e74c3c; }
.empty { color: #555; font-size: 12px; text-align: center; padding: 20px; }
</style>
