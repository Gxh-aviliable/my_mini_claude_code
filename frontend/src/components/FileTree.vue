<template>
  <div class="file-tree">
    <div class="tree-header">
      <span class="tree-title">Files</span>
      <button class="btn-icon" title="Refresh" @click="loadTree">&#x21bb;</button>
      <button class="btn-icon" title="New Folder" @click="newFolder">+&#x1F4C1;</button>
    </div>

    <div v-if="loading" class="tree-loading">Loading...</div>
    <div v-else-if="error" class="tree-error">{{ error }}</div>
    <div v-else class="tree-body">
      <TreeNode
        v-for="node in treeChildren"
        :key="node.path"
        :node="node"
        :depth="0"
        :selected-path="selectedPath"
        @select="$emit('select', $event)"
        @delete="handleDelete"
        @rename="handleRename"
      />
      <div v-if="!treeChildren.length" class="tree-empty">Empty workspace</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import * as api from '../api/client.js'

const props = defineProps({
  selectedPath: { type: String, default: '' }
})
const emit = defineEmits(['select', 'refresh'])

const treeData = ref(null)
const loading = ref(false)
const error = ref('')

const treeChildren = computed(() => treeData.value?.children || [])

async function loadTree() {
  loading.value = true
  error.value = ''
  try {
    treeData.value = await api.fetchTree('', 3)
  } catch (e) {
    error.value = 'Failed to load files'
  } finally {
    loading.value = false
  }
}

function handleDelete(node) {
  if (confirm(`Delete "${node.name}"?`)) {
    api.deleteItem(node.path).then(loadTree).catch(e => alert(e.message))
  }
}

function handleRename(node) {
  const newName = prompt('New name:', node.name)
  if (newName && newName !== node.name) {
    const parentPath = node.path.split('/').slice(0, -1).join('/')
    const newPath = parentPath ? `${parentPath}/${newName}` : newName
    api.moveItem(node.path, newPath).then(loadTree).catch(e => alert(e.message))
  }
}

function newFolder() {
  const name = prompt('Folder name:')
  if (name) {
    const prefix = props.selectedPath || ''
    const fullPath = prefix ? `${prefix}/${name}` : name
    api.createDir(fullPath).then(loadTree).catch(e => alert(e.message))
  }
}

onMounted(loadTree)
defineExpose({ loadTree })
</script>

<style scoped>
.file-tree {
  display: flex; flex-direction: column; height: 100%; overflow: hidden;
}
.tree-header {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 10px; border-bottom: 1px solid #222; font-size: 12px; color: #888;
}
.tree-title { flex: 1; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.btn-icon {
  background: none; border: none; color: #888; cursor: pointer; font-size: 16px; padding: 2px 4px; line-height: 1;
}
.btn-icon:hover { color: #e0e0e0; }
.tree-loading, .tree-error, .tree-empty { padding: 12px; font-size: 12px; color: #666; }
.tree-error { color: #e74c3c; }
.tree-body { flex: 1; overflow-y: auto; padding: 4px 0; }
</style>
