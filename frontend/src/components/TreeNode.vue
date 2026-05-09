<template>
  <div
    :class="['tree-node', { selected: selectedPath === node.path }]"
    :style="{ paddingLeft: (depth * 16 + 8) + 'px' }"
    @click="$emit('select', node)"
    @contextmenu.prevent="showMenu = !showMenu"
  >
    <span v-if="node.type === 'dir'" class="node-icon" @click.stop="expanded = !expanded">
      {{ expanded ? '&#x1F4C2;' : '&#x1F4C1;' }}
    </span>
    <span v-else class="node-icon">&#x1F4C4;</span>
    <span class="node-name">{{ node.name }}</span>

    <div v-if="showMenu" class="ctx-menu">
      <button @click.stop="emit('rename', node); showMenu = false">Rename</button>
      <button @click.stop="emit('delete', node); showMenu = false">Delete</button>
    </div>

    <template v-if="expanded && node.type === 'dir' && node.children">
      <TreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :selected-path="selectedPath"
        @select="$emit('select', $event)"
        @delete="$emit('delete', $event)"
        @rename="$emit('rename', $event)"
      />
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  selectedPath: { type: String, default: '' }
})
const emit = defineEmits(['select', 'delete', 'rename'])

const expanded = ref(false)
const showMenu = ref(false)
</script>

<style scoped>
.tree-node {
  display: flex; align-items: center; gap: 4px; padding: 3px 8px;
  cursor: pointer; font-size: 12px; color: #ccc; position: relative; user-select: none;
}
.tree-node:hover { background: #16213e; }
.tree-node.selected { background: #0f3460; color: #fff; }
.node-icon { font-size: 14px; flex-shrink: 0; }
.node-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ctx-menu {
  position: absolute; right: 8px; top: 100%; background: #1a1a2e; border: 1px solid #333;
  border-radius: 4px; padding: 2px; z-index: 10; display: flex; flex-direction: column;
}
.ctx-menu button {
  background: none; border: none; color: #ccc; padding: 4px 12px; font-size: 11px;
  text-align: left; cursor: pointer; white-space: nowrap;
}
.ctx-menu button:hover { background: #0f3460; }
</style>
