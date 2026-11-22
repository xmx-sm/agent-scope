<template>
  <div class="page">
    <h2 class="page-title">知识库</h2>
    <p class="page-desc">向量库、文档解析、切片预览、共享、检索与日志；Embedding 默认来自「默认配置 → Agent 配置」</p>

    <el-tabs v-model="activeTab" class="kb-tabs">
      <el-tab-pane label="向量库" name="libraries">
        <div class="panel" v-loading="loadingLibraries">
          <div class="toolbar">
            <el-tag v-if="libraries.length" type="info" effect="plain">共 {{ libraries.length }} 个库</el-tag>
            <div class="grow"></div>
            <el-button type="primary" :icon="Plus" @click="openLibraryCreate">创建向量库</el-button>
          </div>
          <el-table :data="libraries" size="small" stripe>
            <el-table-column label="名称" min-width="150">
              <template #default="{ row }">
                <div class="lib-name">
                  <span>{{ row.name }}</span>
                  <el-tag v-if="row.is_shared" size="small" type="warning">共享自 {{ row.owner_name }}</el-tag>
                  <el-tag v-else-if="row.share_count" size="small" type="success">已共享 {{ row.share_count }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="vector_type" label="类型" width="105" />
            <el-table-column prop="document_count" label="文档" width="70" />
            <el-table-column label="切片" width="70">
              <template #default="{ row }">
                <span v-if="row.chunk_count">{{ row.chunk_count }}</span>
                <el-tag v-else-if="row.parse_requested" size="small" type="warning">排队</el-tag>
                <span v-else>0</span>
              </template>
            </el-table-column>
            <el-table-column label="自动解析" width="95">
              <template #default="{ row }">
                <el-tag size="small" :type="row.auto_parse ? 'success' : 'info'">
                  {{ row.auto_parse ? `${row.parse_interval}s` : '关闭' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="权限" width="90">
              <template #default="{ row }">{{ permissionText(row.permission) }}</template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
            <el-table-column label="操作" width="300" fixed="right">
              <template #default="{ row }">
                <template v-if="row.permission === 'owner'">
                  <el-button link type="primary" @click="openLibraryEdit(row)">编辑</el-button>
                  <el-button link type="primary" :loading="testingId === row.id" @click="testLibrary(row)">测试</el-button>
                  <el-button link type="warning" @click="rebuildLibrary(row)">重建</el-button>
                  <el-button link type="primary" @click="openShare(row)">共享</el-button>
                  <el-button link type="danger" @click="deleteLibrary(row)">删除</el-button>
                </template>
                <el-button v-else link type="primary" :loading="testingId === row.id" @click="testLibrary(row)">测试</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!libraries.length && !loadingLibraries" description="暂无向量库" :image-size="70" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="文档" name="documents">
        <div class="panel" v-loading="loadingDocuments">
          <div class="toolbar">
            <el-select v-model="docLibraryId" placeholder="选择向量库" style="width: 230px" @change="loadDocuments">
              <el-option
                v-for="lib in libraries"
                :key="lib.id"
                :label="lib.is_shared ? `${lib.name}（${lib.owner_name} 共享）` : lib.name"
                :value="lib.id"
              />
            </el-select>
            <el-select v-model="docStatus" placeholder="全部状态" clearable style="width: 130px" @change="loadDocuments">
              <el-option label="待解析" value="pending" />
              <el-option label="解析中" value="parsing" />
              <el-option label="已解析" value="parsed" />
              <el-option label="失败" value="failed" />
            </el-select>
            <div class="grow"></div>
            <input ref="fileInput" type="file" hidden multiple @change="uploadDocuments" />
            <el-button
              type="primary"
              :icon="Upload"
              :loading="uploading"
              :disabled="!docLibraryId || !docWritable"
              @click="fileInput.click()"
            >上传文档</el-button>
            <el-button
              :loading="parsingPending"
              :disabled="!docLibraryId || !docWritable"
              @click="parsePending"
            >批量解析</el-button>
            <el-button v-if="auth.isSuperAdmin" @click="openParseConfig">解析配置</el-button>
          </div>
          <el-alert
            v-if="docLibrary && !docWritable"
            type="info"
            :closable="false"
            show-icon
            title="该库为只读共享，不能上传/解析/删除文档"
            style="margin-bottom: 10px"
          />
          <el-table :data="documents" size="small" stripe>
            <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTag(row.status)">{{ statusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="切片" width="70">
              <template #default="{ row }">
                <span v-if="row.chunk_count">{{ row.chunk_count }}</span>
                <el-tag v-else-if="row.parse_requested" size="small" type="warning">排队</el-tag>
                <span v-else>0</span>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="95">
              <template #default="{ row }">{{ bytesText(row.filesize) }}</template>
            </el-table-column>
            <el-table-column label="错误" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.error_message || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="210">
              <template #default="{ row }">
                <el-button link type="primary" @click="previewChunks(row)">切片</el-button>
                <el-button link type="primary" @click="downloadDocument(row)">下载</el-button>
                <el-button
                  v-if="docWritable"
                  link
                  type="primary"
                  :loading="parsingId === row.id"
                  :disabled="row.status === 'parsing'"
                  @click="parseDocument(row)"
                >解析</el-button>
                <el-button v-if="docWritable" link type="danger" @click="deleteDocument(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!documents.length && !loadingDocuments" description="暂无文档" :image-size="70" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="检索" name="search">
        <div class="panel">
          <div class="toolbar">
            <el-select v-model="searchLibs" multiple collapse-tags placeholder="全部可访问库" style="min-width: 220px">
              <el-option
                v-for="lib in libraries"
                :key="lib.id"
                :label="lib.is_shared ? `${lib.name}（共享）` : lib.name"
                :value="lib.id"
              />
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
        <div class="form-grid">
          <el-form-item label="自动解析">
            <el-switch v-model="libraryForm.auto_parse" />
          </el-form-item>
          <el-form-item label="扫描间隔（秒，最小 60）">
            <el-input-number v-model="libraryForm.parse_interval" :min="60" :max="86400" :step="60" />
          </el-form-item>
        </div>
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

    <el-dialog v-model="shareDialog" :title="`共享「${shareLibrary?.name || ''}」`" :width="isMobile ? '94%' : '560px'">
      <div class="toolbar">
        <el-select
          v-model="shareTarget"
          filterable
          remote
          :remote-method="searchCandidates"
          placeholder="搜索用户"
          style="flex: 1"
        >
          <el-option
            v-for="user in candidates"
            :key="user.id"
            :label="`${user.nickname || user.username}（${user.username}）`"
            :value="user.id"
          />
        </el-select>
        <el-select v-model="sharePermission" style="width: 120px">
          <el-option label="只读" value="read" />
          <el-option label="可写" value="read_write" />
        </el-select>
        <el-button type="primary" :disabled="!shareTarget" @click="addShare">共享</el-button>
      </div>
      <el-table :data="shares" size="small">
        <el-table-column prop="target_name" label="用户" min-width="130" />
        <el-table-column prop="target_account" label="账号" min-width="120" />
        <el-table-column label="权限" width="90">
          <template #default="{ row }">{{ row.permission === 'read_write' ? '可写' : '只读' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeShare(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!shares.length" description="尚未共享" :image-size="50" />
      <template #footer><el-button @click="shareDialog = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="parseConfigDialog" title="知识库解析配置" :width="isMobile ? '94%' : '420px'">
      <el-form label-position="top">
        <el-form-item label="同时解析文档数（1~8）">
          <el-input-number v-model="parseConfig.parse_concurrency" :min="1" :max="8" />
        </el-form-item>
        <el-form-item label="排队顺序">
          <el-select v-model="parseConfig.queue_mode" style="width:100%">
            <el-option label="先进先出 FIFO" value="fifo" />
            <el-option label="后进先出 LIFO" value="lifo" />
          </el-select>
        </el-form-item>
        <el-form-item label="后台扫描间隔（秒）">
          <el-input-number v-model="parseConfig.worker_interval" :min="2" :max="60" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="parseConfigDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingParseConfig" @click="saveParseConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="chunkDialog" :title="`切片预览 · ${chunkDoc?.filename || ''}`" :width="isMobile ? '94%' : '760px'">
      <div v-loading="loadingChunks" class="chunk-list">
        <div v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
          <div class="chunk-index">#{{ chunk.index + 1 }}</div>
          <pre>{{ chunk.text }}</pre>
        </div>
        <el-empty v-if="!chunks.length && !loadingChunks" description="暂无切片" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import api from '../utils/api'
import { useAuthStore } from '../stores/auth'

const isMobile = ref(window.innerWidth < 768)
const auth = useAuthStore()
const activeTab = ref('libraries')
const parseConfigDialog = ref(false)
const savingParseConfig = ref(false)
const parseConfig = reactive({ parse_concurrency: 2, queue_mode: 'fifo', worker_interval: 5 })
let pollTimer = null
const libraries = ref([])
const documents = ref([])
const logs = ref([])
const results = ref([])
const searchErrors = ref([])
const loadingLibraries = ref(false)
const loadingDocuments = ref(false)
const loadingLogs = ref(false)
const uploading = ref(false)
const parsingPending = ref(false)
const parsingId = ref('')
const testingId = ref('')
const savingLibrary = ref(false)
const libraryDialog = ref(false)
const libraryEditing = ref(false)
const libraryForm = reactive({
  id: '', name: '', vector_type: 'sqlite', description: '',
  embedding: { provider: '', model: '', base_url: '', api_key: '', dimensions: 0 },
  auto_parse: false, parse_interval: 300
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
const shareDialog = ref(false)
const shareLibrary = ref(null)
const shareTarget = ref('')
const sharePermission = ref('read')
const shares = ref([])
const candidates = ref([])
const chunkDialog = ref(false)
const chunkDoc = ref(null)
const chunks = ref([])
const loadingChunks = ref(false)

const vectorTypes = ['sqlite', 'zvec', 'qdrant', 'milvus', 'faiss', 'chroma', 'pgvector', 'oceanbase', 'mongodb', 'elasticsearch']
const docLibrary = computed(() => libraries.value.find((item) => item.id === docLibraryId.value))
const docWritable = computed(() => ['owner', 'read_write'].includes(docLibrary.value?.permission))

function statusTag(status) {
  return { pending: 'info', parsing: 'warning', parsed: 'success', failed: 'danger' }[status] || 'info'
}
function statusText(status) {
  return { pending: '待解析', parsing: '解析中', parsed: '已解析', failed: '失败' }[status] || status
}
function permissionText(permission) {
  return { owner: '所有者', read: '只读', read_write: '可写' }[permission] || permission
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
    if (!libraries.value.find((item) => item.id === docLibraryId.value)) {
      docLibraryId.value = libraries.value[0]?.id || ''
    }
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
    id: '', name: '', vector_type: 'sqlite', description: '',
    embedding: { provider: '', model: '', base_url: '', api_key: '', dimensions: 0 },
    auto_parse: false, parse_interval: 300
  })
  configText.value = '{"chunk_size":256,"overlap":0}'
  libraryDialog.value = true
}

function openLibraryEdit(row) {
  libraryEditing.value = true
  Object.assign(libraryForm, {
    id: row.id, name: row.name, vector_type: row.vector_type, description: row.description,
    embedding: { ...row.embedding }, auto_parse: row.auto_parse, parse_interval: row.parse_interval
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
        config,
        auto_parse: libraryForm.auto_parse,
        parse_interval: libraryForm.parse_interval
      })
      ElMessage.success('向量库已更新')
    } else {
      await api.post('/agent/knowledge/libraries', {
        name: libraryForm.name,
        vector_type: libraryForm.vector_type,
        description: libraryForm.description,
        embedding: libraryForm.embedding,
        config,
        auto_parse: libraryForm.auto_parse,
        parse_interval: libraryForm.parse_interval
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
    await loadLibraries()
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
    ElMessage.success('已加入解析队列')
    startPolling()
  } catch {
    /* ignore */
  } finally {
    parsingId.value = ''
    await loadDocuments()
  }
}

async function parsePending() {
  parsingPending.value = true
  try {
    const data = await api.post(`/agent/knowledge/libraries/${docLibraryId.value}/parse-pending`)
    ElMessage.success(`已加入队列：${data.queued} 个`)
    startPolling()
    await loadDocuments()
  } catch {
    /* ignore */
  } finally {
    parsingPending.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  let rounds = 0
  pollTimer = setInterval(async () => {
    rounds += 1
    await loadDocuments()
    await loadLibraries()
    if (rounds >= 40) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 3000)
}

async function openParseConfig() {
  try {
    Object.assign(parseConfig, await api.get('/agent/knowledge/parse-config'))
  } catch {
    /* ignore */
  }
  parseConfigDialog.value = true
}

async function saveParseConfig() {
  savingParseConfig.value = true
  try {
    Object.assign(
      parseConfig,
      await api.put('/agent/knowledge/parse-config', { ...parseConfig })
    )
    ElMessage.success('解析配置已保存')
    parseConfigDialog.value = false
  } catch {
    /* ignore */
  } finally {
    savingParseConfig.value = false
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
    await loadLibraries()
  } catch {
    /* ignore */
  }
}

async function previewChunks(row) {
  chunkDoc.value = row
  chunkDialog.value = true
  loadingChunks.value = true
  try {
    const data = await api.get(`/agent/knowledge/documents/${row.id}/chunks`)
    chunks.value = data.chunks
  } catch {
    chunks.value = []
  } finally {
    loadingChunks.value = false
  }
}

async function downloadDocument(row) {
  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE || '/api'}/agent/knowledge/documents/${row.id}/download`,
      { headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` } }
    )
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = row.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.message || '下载失败')
  }
}

async function openShare(row) {
  shareLibrary.value = row
  shareTarget.value = ''
  sharePermission.value = 'read'
  candidates.value = []
  shareDialog.value = true
  await loadShares()
  await searchCandidates('')
}

async function loadShares() {
  if (!shareLibrary.value) return
  try {
    shares.value = await api.get(`/agent/knowledge/libraries/${shareLibrary.value.id}/shares`)
  } catch {
    shares.value = []
  }
}

async function searchCandidates(keyword) {
  try {
    candidates.value = await api.get('/agent/knowledge/share-candidates', {
      params: { q: keyword || '' }
    })
  } catch {
    candidates.value = []
  }
}

async function addShare() {
  try {
    await api.post(`/agent/knowledge/libraries/${shareLibrary.value.id}/shares`, {
      target_user_id: shareTarget.value,
      permission: sharePermission.value
    })
    ElMessage.success('已共享')
    shareTarget.value = ''
    await loadShares()
    await loadLibraries()
  } catch {
    /* ignore */
  }
}

async function removeShare(row) {
  try {
    await api.delete(
      `/agent/knowledge/libraries/${shareLibrary.value.id}/shares/${row.target_user_id}`
    )
    ElMessage.success('已取消共享')
    await loadShares()
    await loadLibraries()
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
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0 18px; }
.lib-name { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.search-results { display: flex; flex-direction: column; gap: 10px; }
.search-item { border: 1px solid var(--app-border); border-radius: 10px; padding: 10px 12px; }
.search-meta { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; }
.search-item pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; }
.search-errors { margin-bottom: 10px; }
.chunk-list { max-height: 62vh; overflow: auto; display: flex; flex-direction: column; gap: 10px; }
.chunk-item { border: 1px solid var(--app-border); border-radius: 10px; padding: 8px 12px; }
.chunk-index { font-size: 12px; color: var(--app-muted); margin-bottom: 6px; }
.chunk-item pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; }
</style>
