<template>
  <div class="page">
    <h2 class="page-title">知识库</h2>
    <p class="page-desc">文档切分、向量化与检索；Embedding 模型在「默认配置 → Agent 配置」中设置</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <el-input v-model="collection" placeholder="集合名，默认 default" style="width: 220px" />
        <input ref="fileInput" type="file" hidden multiple @change="upload" />
        <el-button type="primary" :icon="Upload" :loading="uploading" @click="fileInput.click()">
          上传文档
        </el-button>
        <el-button @click="loadAll">刷新</el-button>
      </div>

      <div class="libs">
        <span class="muted">已有集合：</span>
        <el-tag
          v-for="lib in libraries"
          :key="libName(lib)"
          :effect="libName(lib) === collection ? 'dark' : 'plain'"
          class="lib-tag"
          closable
          @click="selectLibrary(lib)"
          @close="deleteLibrary(lib)"
        >
          {{ libName(lib) }}
        </el-tag>
        <span v-if="!libraries.length" class="muted">暂无</span>
      </div>
    </div>

    <div class="panel">
      <div class="toolbar">
        <el-input v-model="query" placeholder="输入问题检索知识库" clearable @keyup.enter="search" />
        <el-input-number v-model="topK" :min="1" :max="20" />
        <el-button type="primary" :loading="searching" @click="search">检索</el-button>
      </div>
      <div v-if="results.length" class="search-results">
        <div v-for="(item, index) in results" :key="index" class="search-item">
          <div class="score">#{{ index + 1 }} · {{ item.score?.toFixed?.(3) ?? item.score ?? '' }}</div>
          <pre>{{ item.text || item.content || JSON.stringify(item) }}</pre>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3 class="card-title">文档列表 · {{ collection }}</h3>
      <el-table :data="documents" size="small" stripe>
        <el-table-column prop="document_id" label="文档" min-width="220" />
        <el-table-column prop="chunk_count" label="切片数" width="100" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeDocument(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!documents.length" description="暂无文档" :image-size="70" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import api from '../utils/api'

const loading = ref(false)
const uploading = ref(false)
const searching = ref(false)
const collection = ref('default')
const libraries = ref([])
const documents = ref([])
const results = ref([])
const query = ref('')
const topK = ref(5)
const fileInput = ref(null)

function libName(lib) {
  return typeof lib === 'string' ? lib : lib.name || lib.collection || lib.path || 'default'
}

async function loadLibraries() {
  try {
    libraries.value = await api.get('/agent/rag/libraries')
  } catch {
    libraries.value = []
  }
}

async function loadDocuments() {
  try {
    documents.value = await api.get('/agent/rag/documents', {
      params: { collection: collection.value }
    })
  } catch {
    documents.value = []
  }
}

async function loadAll() {
  loading.value = true
  try {
    await loadLibraries()
    await loadDocuments()
  } finally {
    loading.value = false
  }
}

function selectLibrary(lib) {
  collection.value = libName(lib)
  loadDocuments()
}

async function upload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      form.append('collection', collection.value || 'default')
      await api.post('/agent/rag/upload', form)
    }
    ElMessage.success('文档已入库')
    await loadAll()
  } catch {
    /* ignore */
  } finally {
    uploading.value = false
  }
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    results.value = await api.post('/agent/rag/search', {
      query: query.value,
      collection: collection.value || 'default',
      top_k: topK.value
    })
  } catch {
    results.value = []
  } finally {
    searching.value = false
  }
}

async function removeDocument(row) {
  try {
    await ElMessageBox.confirm(`删除文档「${row.document_id}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete('/agent/rag/documents', {
      params: { collection: collection.value, doc_id: row.document_id }
    })
    ElMessage.success('文档已删除')
    await loadDocuments()
  } catch {
    /* ignore */
  }
}

async function deleteLibrary(lib) {
  const name = libName(lib)
  try {
    await ElMessageBox.confirm(`删除集合「${name}」及其全部文档？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/rag/libraries/${encodeURIComponent(name)}`)
    ElMessage.success('集合已删除')
    await loadAll()
  } catch {
    /* ignore */
  }
}

onMounted(loadAll)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.libs {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.lib-tag {
  cursor: pointer;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search-item {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 10px 12px;
}

.score {
  font-size: 12px;
  color: var(--app-muted);
  margin-bottom: 6px;
}

.search-item pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 13px;
}

.card-title {
  margin: 0 0 12px;
  font-size: 15px;
}
</style>
