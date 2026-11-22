<template>
  <div class="page">
    <h2 class="page-title">知识库</h2>
    <p class="page-desc">向量库、文档解析、检索与操作日志；Embedding 默认来自「默认配置 → Agent 配置」</p>

    <el-tabs v-model="activeTab" class="kb-tabs">
      <!-- 向量库 -->
      <el-tab-pane label="向量库" name="libraries">
        <div class="panel" v-loading="loadingLibraries">
          <div class="toolbar">
            <div class="grow"></div>
            <el-button type="primary" :icon="Plus" @click="openLibraryCreate">创建向量库</el-button>
          </div>
          <el-table :data="libraries" size="small" stripe>
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column prop="vector_type" label="类型" width="110" />
            <el-table-column prop="document_count" label="文档" width="80" />
            <el-table-column prop="chunk_count" label="切片" width="80" />
            <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openLibraryEdit(row)">编辑</el-button>
                <el-button link type="primary" :loading="testingId === row.id" @click="testLibrary(row)">测试</el-button>
                <el-button link type="warning" @click="rebuildLibrary(row)">重建</el-button>
                <el-button link type="danger" @click="deleteLibrary(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!libraries.length && !loadingLibraries" description="暂无向量库" :image-size="70" />
        </div>
      </el-tab-pane>

      <!-- 文档 -->
      <el-tab-pane label="文档" name="documents">
        <div class="panel" v-loading="loadingDocuments">
          <div class="toolbar">
            <el-select v-model="docLibraryId" placeholder="选择向量库" style="width: 220px" @change="loadDocuments">
              <el-option v-for="lib in libraries" :key="lib.id" :label="lib.name" :value="lib.id" />
            </el-select>
            <el-select v-model="docStatus" placeholder="全部状态" clearable style="width: 140px" @change="loadDocuments">
              <el-option label="待解析" value="pending" />
              <el-option label="解析中" value="parsing" />
              <el-option label="已解析" value="parsed" />
              <el-option label="失败" value="failed" />
            </el-select>
            <input ref="fileInput" type="file" hidden multiple @change="uploadDocuments" />
            <el-button type="primary" :icon="Upload" :loading="uploading" :disabled="!docLibraryId" @click="fileInput.click()">
              上传文档
            </el-button>
          </div>
          <el-table :data="documents" size="small" stripe>
            <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTag(row.status)">{{ statusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="切片" width="80" />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ bytesText(row.filesize) }}</template>
            </el-table-column>
            <el-table-column label="错误" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.error_message || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button link type="primary" :loading="parsingId === row.id" :disabled="row.status === 'parsing'" @click="parseDocument(row)">
                  解析
                </el-button>
                <el-button link type="danger" @click="deleteDocument(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!documents.length && !loadingDocuments" description="暂无文档" :image-size="70" />
        </div>
      </el-tab-pane>

      <!-- 检索 -->
      <el-tab-pane label="检索" name="search">
        <div class="panel">
          <div class="toolbar">
            <el-select v-model="searchLibs" multiple collapse-tags placeholder="全部库" style="min-width: 220px">
              <el-option v-for="lib in libraries" :key="lib.id" :label="lib.name" :value="lib.id" />
            </el-select>
            <el-input v-model="query" placeholder="输入问题" clearable @keyup.enter="search" />
            <el-input-number v-model="topK" :min="1" :max="50" />
            <el-button type="primary" :loading="searching" @click="search">检索</el-button>
          </div>
          <div v-if="searchErrors.length" class="search-errors">
            <el-alert
              v-for="(err, i) in searchErrors"
              :key="i"
              type="warning"
              :closable="false"
              show-icon
              :title="`${err.library_name}: ${err.error}`"
            />
          </div>
          <div v-if="results.length" class="search-results">
            <div v-for="(item, index) in results" :key="index" class="search-item">
              <div class="search-meta">
                <el-tag size="small" effect="plain">{{ item.library_name }}</el-tag>
                <span class="muted">score {{ Number(item.score || 0).toFixed(4) }}</span>
              </div>
              <pre>{{ item.text || item.content || JSON.stringify(item) }}</pre>
            </div>
          </div>
          <el-empty v-else description="暂无结果" :image-size="60" />
        </div>
      </el-tab-pane>

      <!-- 日志 -->
      <el-tab-pane label="日志" name="logs">
        <div class="panel" v-loading="loadingLogs">
          <div class="toolbar">
            <el-select v-model="logLibraryId" placeholder="全部库" clearable style="width: 200px" @change="loadLogs">
              <el-option v-for="lib in libraries" :key="lib.id" :label="lib.name" :value="lib.id" />
            </el-select>
            <el-button @click="loadLogs">刷新</el-button>
          </div>
          <el-table :data="logs" size="small" stripe>
            <el-table-column prop="operation" label="操作" width="120" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="details" label="详情" min-width="220" show-overflow-tooltip />
            <el-table-column prop="error_message" label="错误" min-width="160" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="180" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 向量库编辑 -->
    <el-dialog v-model="libraryDialog" :title="libraryEditing ? '编辑向量库' : '创建向量库'" :width="isMobile ? '94%' : '620px'">
      <el-form :model="libraryForm" label-position="top">
        <div class="form-grid">
          <el-form-item label="名称">
            <el-input v-model="libraryForm.name" :disabled="libraryEditing" placeholder="中英文/数字/_/-" />
          </el-form-item>
          <el-form-item label="向量库类型">
            <el-select v-model="libraryForm.vector_type" :disabled="libraryEditing" style="width: 100%">
              <el-option v-for="type in vectorTypes" :key="type" :label="type" :value="type" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="描述"><el-input v-model="libraryForm.description" /></el-form-item>
        <el-divider content-position="left">Embedding（留空跟随系统）</el-divider>
        <div class="form-grid">
          <el-form-item label="服务商"><el-input v-model="libraryForm.embedding.provider" placeholder="openai-compatible" /></el-form-item>
          <el-form-item label="模型"><el-input v-model="libraryForm.embedding.model" placeholder="text-embedding-..." /></el-form-item>
          <el-form-item label="API 地址"><el-input v-model="libraryForm.embedding.base_url" /></el-form-item>
          <el-form-item label="API Key"><el-input v-model="libraryForm.embedding.api_key" type="password" show-password /></el-form-item>
          <el-form-item label="维度"><el-input-number v-model="libraryForm.embedding.dimensions" :min="0" /></el-form-item>
        </div>
        <el-form-item label="切分配置（JSON）">
          <el-input v-model="configText" type="textarea" :rows="3" placeholder='{"chunk_size":256,"overlap":0}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="libraryDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingLibrary" @click="saveLibrary">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const activeTab = ref('libraries')
const libraries = ref([])
const documents = ref([])
const logs = ref([])
const results = ref([])
const searchErrors = ref([])
const loadingLibraries = ref(false)
const loadingDocuments = ref(false)
const loadingLogs = ref(false)
const uploading = ref(false)
const parsingId = ref('')
const testingId = ref('')
const savingLibrary = ref(false)
const libraryDialog = ref(false)
const libraryEditing = ref(false)
const libraryForm = reactive({
  id: '',
  name: '',
  vector_type: 'sqlite',
  description: '',
  embedding: { provider: '', model: '', base_url: '', api_key: '', dimensions: 0 }
})
const configText = ref('{"chunk_size":256,"overlap":0}')
const docLibraryId = ref('')
const docStatus = ref('')
const logLibraryId = ref('')
const searchLibs = ref([])
const query = ref('')
const topK = ref(5)
const searching = ref(false)
const fileInput = ref(null)

const vectorTypes = ['sqlite', 'zvec', 'qdrant', 'milvus', 'faiss', 'chroma', 'pgvector', 'oceanbase', 'mongodb', 'elasticsearch']

function statusTag(status) {
  return { pending: 'info', parsing: 'warning', parsed: 'success', failed: 'danger' }[status] || 'info'
}
function statusText(status) {
  return { pending: '待解析', parsing: '解析中', parsed: '已解析', failed: '失败' }[status] || status
}
function bytesText(value) {
  const num = Number(value || 0)
  if (num >= 1024 * 1024) return `${(num / 1024 / 1024).toFixed(1)} MB`
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`
  return `${num} B`
}

async function loadLibraries() {
  loadingLibraries.value = true
  try {
    libraries.value = await api.get('/agent/knowledge/libraries')
    if (!docLibraryId.value && libraries.value.length) docLibraryId.value = libraries.value[0].id
  } catch {
    /* ignore */
  } finally {
    loadingLibraries.value = false
  }
}

async function loadDocuments() {
  if (!docLibraryId.value) return
  loadingDocuments.value = true
  try {
    const data = await api.get('/agent/knowledge/documents', {
      params: { library_id: docLibraryId.value, status: docStatus.value }
    })
    documents.value = data.documents
  } catch {
    /* ignore */
  } finally {
    loadingDocuments.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const data = await api.get('/agent/knowledge/logs', { params: { library_id: logLibraryId.value } })
    logs.value = data.logs
  } catch {
    /* ignore */
  } finally {
    loadingLogs.value = false
  }
}

function openLibraryCreate() {
  libraryEditing.value = false
  Object.assign(libraryForm, {
    id: '',
    name: '',
    vector_type: 'sqlite',
    description: '',
    embedding: { provider: '', model: '', base_url: '', api_key: '', dimensions: 0 }
  })
  configText.value = '{"chunk_size":256,"overlap":0}'
  libraryDialog.value = true
}

function openLibraryEdit(row) {
  libraryEditing.value = true
  Object.assign(libraryForm, {
    id: row.id,
    name: row.name,
    vector_type: row.vector_type,
    description: row.description,
    embedding: { ...row.embedding }
  })
  configText.value = JSON.stringify(row.config || {}, null, 2)
  libraryDialog.value = true
}

async function saveLibrary() {
  let config = {}
  try {
    config = JSON.parse(configText.value || '{}')
  } catch {
    ElMessage.error('切分配置不是合法 JSON')
    return
  }
  savingLibrary.value = true
  try {
    if (libraryEditing.value) {
      await api.put(`/agent/knowledge/libraries/${libraryForm.id}`, {
        description: libraryForm.description,
        embedding: libraryForm.embedding,
        config
      })
      ElMessage.success('向量库已更新')
    } else {
      await api.post('/agent/knowledge/libraries', {
        name: libraryForm.name,
        vector_type: libraryForm.vector_type,
        description: libraryForm.description,
        embedding: libraryForm.embedding,
        config
      })
      ElMessage.success('向量库已创建')
    }
    libraryDialog.value = false
    await loadLibraries()
  } catch {
    /* ignore */
  } finally {
    savingLibrary.value = false
  }
}

async function deleteLibrary(row) {
  try {
    await ElMessageBox.confirm(`删除向量库「${row.name}」及全部文档？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/knowledge/libraries/${row.id}`)
    ElMessage.success('已删除')
    await loadLibraries()
  } catch {
    /* ignore */
  }
}

async function testLibrary(row) {
  testingId.value = row.id
  try {
    const data = await api.post(`/agent/knowledge/libraries/${row.id}/test`)
    ElMessage.success(`连接成功，集合数 ${data.collections?.length || 0}`)
  } catch {
    /* ignore */
  } finally {
    testingId.value = ''
  }
}

async function rebuildLibrary(row) {
  try {
    await ElMessageBox.confirm(`重建「${row.name}」索引？文档会回到待解析。`, '重建确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.post(`/agent/knowledge/libraries/${row.id}/rebuild`)
    ElMessage.success('已重建，请重新解析文档')
    await loadLibraries()
  } catch {
    /* ignore */
  }
}

async function uploadDocuments(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length || !docLibraryId.value) return
  uploading.value = true
  try {
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      form.append('library_id', docLibraryId.value)
      await api.post('/agent/knowledge/documents/upload', form)
    }
    ElMessage.success('上传完成')
    await loadDocuments()
  } catch {
    /* ignore */
  } finally {
    uploading.value = false
  }
}

async function parseDocument(row) {
  parsingId.value = row.id
  try {
    await api.post(`/agent/knowledge/documents/${row.id}/parse`)
    ElMessage.success('解析完成')
  } catch {
    /* ignore */
  } finally {
    parsingId.value = ''
    await loadDocuments()
  }
}

async function deleteDocument(row) {
  try {
    await ElMessageBox.confirm(`删除文档「${row.filename}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/knowledge/documents/${row.id}`)
    ElMessage.success('已删除')
    await loadDocuments()
  } catch {
    /* ignore */
  }
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const data = await api.post('/agent/knowledge/search', {
      query: query.value,
      library_ids: searchLibs.value,
      top_k: topK.value
    })
    results.value = data.results
    searchErrors.value = data.errors || []
  } catch {
    results.value = []
  } finally {
    searching.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'documents' && !documents.value.length) loadDocuments()
  if (tab === 'logs') loadLogs()
})

onMounted(async () => {
  await loadLibraries()
  if (libraries.value.length) docLibraryId.value = libraries.value[0].id
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 18px;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search-item {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 10px 12px;
}

.search-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}

.search-item pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.search-errors {
  margin-bottom: 10px;
}
</style>
