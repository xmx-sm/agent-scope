<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">长期记忆</h2>
        <p class="page-desc">本地 Markdown 文件记忆，跨会话生效；可按用户开关、查看和清理。</p>
      </div>
      <el-switch
        v-model="enabled"
        active-text="启用"
        inactive-text="关闭"
        :loading="saving"
        @change="toggle"
      />
    </div>

    <div class="panel" v-loading="loading">
      <div class="status-grid">
        <div class="status-item">
          <span class="muted">当前来源</span>
          <strong>{{ status.source === 'user' ? '个人设置' : '系统默认' }}</strong>
        </div>
        <div class="status-item">
          <span class="muted">文件数</span>
          <strong>{{ status.file_count || 0 }}</strong>
        </div>
        <div class="status-item">
          <span class="muted">占用</span>
          <strong>{{ bytesText(status.bytes) }}</strong>
        </div>
        <div class="status-item">
          <span class="muted">最近更新</span>
          <strong>{{ status.last_modified || '—' }}</strong>
        </div>
      </div>
      <div class="memory-path">
        <span class="muted">存储目录</span>
        <code>{{ status.path || '—' }}</code>
      </div>

      <div class="toolbar">
        <el-tag :type="enabled ? 'success' : 'info'" effect="plain">
          {{ enabled ? '记忆已启用' : '记忆已关闭' }}
        </el-tag>
        <div class="grow"></div>
        <el-button type="primary" plain :icon="Plus" @click="openCreate">新建记忆</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button type="danger" plain :disabled="!files.length" @click="clearAll">清空记忆</el-button>
      </div>

      <el-table :data="files" size="small" stripe>
        <el-table-column prop="name" label="文件" min-width="240" show-overflow-tooltip />
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ bytesText(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="modified_at" label="更新时间" width="190" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="preview(row)">查看</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!files.length && !loading" description="暂无长期记忆文件" :image-size="70" />
    </div>

    <el-dialog v-model="dialog" :title="previewFile?.name || '记忆内容'" :width="isMobile ? '94%' : '760px'">
      <pre class="memory-content">{{ content || '（空）' }}</pre>
      <template #footer>
        <el-button @click="dialog = false">关闭</el-button>
        <el-button type="primary" @click="editCurrent">编辑</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editorDialog"
      :title="editorNew ? '新建记忆' : '编辑记忆'"
      :width="isMobile ? '94%' : '760px'"
      @closed="editorName = ''"
    >
      <el-form label-position="top">
        <el-form-item label="文件路径">
          <el-input v-model="editorName" :disabled="!editorNew" placeholder="Memory/notes.md" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editorContent" type="textarea" :rows="18" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorDialog = false">取消</el-button>
        <el-button type="primary" :loading="editorSaving" @click="saveEditor">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const saving = ref(false)
const enabled = ref(false)
const files = ref([])
const status = reactive({
  enabled: false,
  source: 'system',
  path: '',
  file_count: 0,
  bytes: 0,
  last_modified: null
})
const dialog = ref(false)
const previewFile = ref(null)
const content = ref('')
const editorDialog = ref(false)
const editorNew = ref(false)
const editorName = ref('')
const editorContent = ref('')
const editorSaving = ref(false)

function bytesText(value) {
  const num = Number(value || 0)
  if (num >= 1024 * 1024) return `${(num / 1024 / 1024).toFixed(1)} MB`
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`
  return `${num} B`
}

async function load() {
  loading.value = true
  try {
    const data = await api.get('/agent/memory')
    Object.assign(status, data)
    enabled.value = Boolean(data.enabled)
    files.value = await api.get('/agent/memory/files')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function toggle(value) {
  saving.value = true
  try {
    const data = await api.put('/agent/memory', { enabled: value })
    Object.assign(status, data)
    enabled.value = Boolean(data.enabled)
    ElMessage.success(value ? '长期记忆已启用' : '长期记忆已关闭')
  } catch {
    enabled.value = !value
  } finally {
    saving.value = false
  }
}

async function preview(row) {
  previewFile.value = row
  content.value = ''
  dialog.value = true
  try {
    const data = await api.get(`/agent/memory/files/${encodeURIComponent(row.name)}`)
    content.value = data.content
  } catch {
    /* ignore */
  }
}

function openCreate() {
  editorNew.value = true
  editorName.value = 'Memory/notes.md'
  editorContent.value = '# 长期记忆\n\n'
  editorDialog.value = true
}

async function openEdit(row) {
  editorNew.value = false
  editorName.value = row.name
  editorContent.value = ''
  editorDialog.value = true
  try {
    const data = await api.get(`/agent/memory/files/${encodeURIComponent(row.name)}`)
    editorContent.value = data.content
  } catch {
    /* ignore */
  }
}

function editCurrent() {
  if (!previewFile.value) return
  const row = previewFile.value
  dialog.value = false
  openEdit(row)
}

async function saveEditor() {
  const name = editorName.value.trim()
  if (!name) return ElMessage.error('请填写文件路径')
  if (!/\.(md|txt)$/i.test(name)) return ElMessage.error('记忆文件只支持 .md / .txt')
  if (new TextEncoder().encode(editorContent.value).length > 512 * 1024) {
    return ElMessage.error('记忆文件不能超过 512KB')
  }
  editorSaving.value = true
  try {
    await api.put(`/agent/memory/files/${encodeURIComponent(name)}`, {
      content: editorContent.value
    })
    ElMessage.success('记忆文件已保存')
    editorDialog.value = false
    await load()
  } catch {
    /* ignore */
  } finally {
    editorSaving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除记忆文件「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/memory/files/${encodeURIComponent(row.name)}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* ignore */
  }
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('清空全部长期记忆？该操作不可恢复。', '清空记忆', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete('/agent/memory')
    ElMessage.success('已清空')
    await load()
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.status-item {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.memory-path {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.memory-path code {
  background: var(--app-bg);
  padding: 4px 8px;
  border-radius: 6px;
  word-break: break-all;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.memory-content {
  margin: 0;
  max-height: 62vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
}
</style>
