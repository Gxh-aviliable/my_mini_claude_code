<template>
  <div class="file-manager">
    <!-- Path Bar -->
    <div class="path-bar">
      <button class="btn-path" @click="navigateTo('')">~</button>
      <template v-for="(seg, i) in pathSegments" :key="i">
        <span class="path-sep">/</span>
        <button class="btn-path" @click="navigateTo(pathSegments.slice(0, i + 1).join('/'))">
          {{ seg }}
        </button>
      </template>
      <span class="path-spacer"></span>
      <button class="btn-action" @click="$emit('refresh')" title="Refresh">&#x21bb;</button>
    </div>

    <!-- File Table -->
    <div class="file-table-wrapper">
      <table class="file-table">
        <thead>
          <tr>
            <th class="col-name">Name</th>
            <th class="col-size">Size</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="currentPath" class="row-dir" @click="parentDir">
            <td colspan="3">&#x1F4C1; ..</td>
          </tr>
          <tr
            v-for="item in currentItems"
            :key="item.path"
            :class="{ selected: previewFile?.path === item.path }"
            @click="handleItemClick(item)"
          >
            <td class="col-name">
              <span class="item-icon">{{ item.type === 'dir' ? '&#x1F4C1;' : '&#x1F4C4;' }}</span>
              {{ item.name }}
            </td>
            <td class="col-size">{{ item.type === 'dir' ? '' : formatSize(item.size) }}</td>
            <td class="col-actions">
              <button class="btn-sm" @click.stop="downloadItem(item)">&#x2B07;</button>
              <button class="btn-sm btn-danger" @click.stop="deleteItem(item)">&#x2715;</button>
            </td>
          </tr>
          <tr v-if="!currentItems.length">
            <td colspan="3" class="empty-msg">Empty directory</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Divider -->
    <div class="preview-divider">
      <span class="preview-label">
        Preview
        <template v-if="previewFile">: {{ previewFile.name }}</template>
      </span>
    </div>

    <!-- Preview -->
    <div class="preview-area">
      <div v-if="!previewFile" class="preview-empty">Select a file to preview</div>
      <div v-else-if="previewContent?.binary" class="preview-empty">
        Binary file ({{ formatSize(previewContent.size) }})
        <br />
        <button class="btn-action" @click="downloadItem(previewFile)">Download</button>
      </div>
      <pre v-else class="preview-code"><code>{{ previewContent?.content || '(empty)' }}</code></pre>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <label class="btn-upload">
        &#x2B06; Upload
        <input type="file" hidden @change="handleUpload" multiple />
      </label>
      <button class="btn-action" @click="newFolder">+ Folder</button>
      <button class="btn-action" @click="downloadSelected" :disabled="!selectedCount">
        &#x2B07; Download {{ selectedCount ? `(${selectedCount})` : '' }}
      </button>
      <button class="btn-action btn-danger" @click="deleteSelected" :disabled="!selectedCount">
        &#x2715; Delete {{ selectedCount ? `(${selectedCount})` : '' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import * as api from '../api/client.js'

const emit = defineEmits(['refresh'])

const currentPath = ref('')
const items = ref([])
const previewFile = ref(null)
const previewContent = ref(null)
const selectedItems = ref(new Set())

const pathSegments = computed(() =>
  currentPath.value ? currentPath.value.split('/').filter(Boolean) : []
)

const currentItems = computed(() =>
  items.value.filter(item => item.type === 'dir').concat(
    items.value.filter(item => item.type === 'file')
  )
)

const selectedCount = computed(() => selectedItems.value.size)

function formatSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

async function loadDir(path) {
  try {
    const tree = await api.fetchTree(path || '', 1)
    items.value = tree?.children || []
    items.value.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  } catch (e) {
    items.value = []
  }
}

function navigateTo(path) {
  currentPath.value = path
  previewFile.value = null
  previewContent.value = null
  selectedItems.value.clear()
  loadDir(path)
}

function parentDir() {
  if (!currentPath.value) return
  const parent = currentPath.value.split('/').slice(0, -1).join('/')
  navigateTo(parent)
}

function handleItemClick(item) {
  if (item.type === 'dir') {
    navigateTo(item.path)
  } else {
    previewFile.value = item
    loadPreview(item)
  }
}

async function loadPreview(item) {
  try {
    previewContent.value = await api.readFile(item.path)
  } catch (e) {
    previewContent.value = { content: `Error: ${e.message}` }
  }
}

async function downloadItem(item) {
  try {
    const blob = await api.downloadFile(item.path)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = item.name; document.body.appendChild(a)
    a.click(); document.body.removeChild(a); URL.revokeObjectURL(url)
  } catch (e) {
    alert(e.message)
  }
}

async function deleteItem(item) {
  if (!confirm(`Delete "${item.name}"?`)) return
  try {
    await api.deleteItem(item.path)
    loadDir(currentPath.value)
    if (previewFile.value?.path === item.path) {
      previewFile.value = null
      previewContent.value = null
    }
    emit('refresh')
  } catch (e) { alert(e.message) }
}

async function newFolder() {
  const name = prompt('Folder name:')
  if (!name) return
  const fullPath = currentPath.value ? `${currentPath.value}/${name}` : name
  try {
    await api.createDir(fullPath)
    loadDir(currentPath.value)
    emit('refresh')
  } catch (e) { alert(e.message) }
}

async function handleUpload(e) {
  const files = e.target.files
  if (!files?.length) return
  try {
    for (const file of files) {
      await api.uploadFile(file, currentPath.value)
    }
    loadDir(currentPath.value)
    emit('refresh')
  } catch (e) { alert(e.message) }
}

async function downloadSelected() {
  if (!selectedItems.value.size) return
  try {
    const paths = Array.from(selectedItems.value)
    const blob = await api.downloadZip(paths, 'export')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'export.zip'; document.body.appendChild(a)
    a.click(); document.body.removeChild(a); URL.revokeObjectURL(url)
  } catch (e) { alert(e.message) }
}

function deleteSelected() {
  if (!selectedItems.value.size) return
  if (!confirm(`Delete ${selectedItems.value.size} item(s)?`)) return
  Promise.all([...selectedItems.value].map(p => api.deleteItem(p).catch(() => {})))
    .then(() => {
      selectedItems.value.clear()
      loadDir(currentPath.value)
      emit('refresh')
    })
}

watch(() => currentPath.value, () => {
  selectedItems.value.clear()
})

// Initial load
loadDir('')
</script>

<style scoped>
.file-manager {
  display: flex; flex-direction: column; height: 100%; overflow: hidden; background: #1a1a2e;
}

/* Path Bar */
.path-bar {
  display: flex; align-items: center; gap: 2px; padding: 6px 10px;
  background: #16213e; border-bottom: 1px solid #222; font-size: 13px; flex-shrink: 0;
}
.btn-path { background: none; border: none; color: #54a0ff; cursor: pointer; font-size: 12px; font-family: monospace; }
.btn-path:hover { text-decoration: underline; }
.path-sep { color: #555; font-size: 12px; }
.path-spacer { flex: 1; }

/* File Table */
.file-table-wrapper { flex: 1; overflow-y: auto; min-height: 0; }
.file-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.file-table th { padding: 6px 10px; text-align: left; color: #888; font-weight: 600; border-bottom: 1px solid #222; position: sticky; top: 0; background: #1a1a2e; }
.file-table td { padding: 5px 10px; border-bottom: 1px solid #111; cursor: pointer; }
.file-table tr:hover td { background: #16213e; }
.file-table tr.selected td { background: #0f3460; }
.col-name { width: auto; }
.col-size { width: 80px; color: #888; }
.col-actions { width: 70px; text-align: right; }
.item-icon { margin-right: 4px; }

/* Preview */
.preview-divider {
  padding: 6px 10px; background: #16213e; border-top: 1px solid #222; border-bottom: 1px solid #222;
  font-size: 11px; color: #888; flex-shrink: 0;
}
.preview-area { height: 200px; overflow: auto; flex-shrink: 0; }
.preview-code {
  padding: 10px; margin: 0; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
  color: #ddd; white-space: pre-wrap; word-break: break-all; line-height: 1.4;
}
.preview-empty { padding: 20px; text-align: center; color: #666; font-size: 12px; }

/* Toolbar */
.toolbar {
  display: flex; gap: 8px; padding: 8px 10px;
  background: #16213e; border-top: 1px solid #222; flex-shrink: 0;
}
.btn-action {
  background: #0f3460; border: none; border-radius: 4px; color: #ddd;
  padding: 5px 12px; font-size: 11px; cursor: pointer;
}
.btn-action:hover:not(:disabled) { background: #1a4a7a; }
.btn-action:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-upload {
  background: #0f3460; border: none; border-radius: 4px; color: #ddd;
  padding: 5px 12px; font-size: 11px; cursor: pointer; display: inline-flex; align-items: center;
}
.btn-upload:hover { background: #1a4a7a; }
.btn-danger { color: #e74c3c; }
.btn-danger:hover:not(:disabled) { background: #4a1a1a; }

.btn-sm {
  background: none; border: none; color: #888; cursor: pointer; font-size: 12px; padding: 1px 4px;
}
.btn-sm:hover { color: #e0e0e0; }

.empty-msg { color: #666; text-align: center; padding: 20px !important; }
</style>
