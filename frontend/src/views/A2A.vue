<template>
  <div class="page">
    <h2 class="page-title">A2A 协作</h2>
    <p class="page-desc">
      局域网内 Agent 互联：对方用 X-Api-Key 调用本机智能体；出站调用会复用本机与对方的 Agent 配置。
    </p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加伙伴</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-table :data="peers" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column prop="direction" label="方向" width="90" />
        <el-table-column prop="endpoint" label="Endpoint" min-width="200" show-overflow-tooltip />
        <el-table-column label="工具" width="80">
          <template #default="{ row }">{{ row.allow_tools ? '允许' : '纯对话' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" :loading="testingId === row.id" @click="testPeer(row)">测试</el-button>
            <el-button link type="primary" @click="reveal(row)">密钥</el-button>
            <el-button link type="warning" @click="rotate(row)">重置</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!peers.length && !loading" description="还没有 A2A 伙伴" :image-size="70" />
    </div>

    <div class="panel" style="margin-top: 16px">
      <h3 class="section-title">调用留痕</h3>
      <el-table :data="invocations" size="small" stripe>
        <el-table-column prop="peer_name" label="伙伴" width="120" />
        <el-table-column prop="direction" label="方向" width="70" />
        <el-table-column prop="status" label="状态" width="80" />
        <el-table-column prop="prompt" label="请求" min-width="180" show-overflow-tooltip />
        <el-table-column prop="response" label="回复" min-width="220" show-overflow-tooltip />
        <el-table-column prop="elapsed_ms" label="耗时(ms)" width="90" />
        <el-table-column prop="created_at" label="时间" width="175" />
      </el-table>
      <el-empty v-if="!invocations.length" description="暂无调用" :image-size="60" />
    </div>

    <el-dialog v-model="dialog" :title="form.id ? '编辑伙伴' : '添加伙伴'" :width="isMobile ? '94%' : '640px'">
      <el-form :model="form" label-position="top">
        <div class="grid">
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="方向">
            <el-select v-model="form.direction" style="width: 100%">
              <el-option label="出站：我调用对方" value="outbound" />
              <el-option label="入站：对方调用我" value="inbound" />
              <el-option label="双向" value="both" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="描述"><el-input v-model="form.description" /></el-form-item>
        <el-form-item label="Endpoint（站点根地址，不带 /a2a）">
          <el-input v-model="form.endpoint" placeholder="http://192.168.1.20:8000" />
        </el-form-item>
        <div class="grid">
          <el-form-item label="对方智能体名（出站可填）">
            <el-input v-model="form.remote_name" placeholder="留空使用伙伴名称" />
          </el-form-item>
          <el-form-item label="协议">
            <el-select v-model="form.protocol" style="width: 100%">
              <el-option label="A2A Lite" value="lite" />
              <el-option label="Standard（当前按 Lite 调用）" value="standard" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="API Key（编辑时留空表示不修改）">
          <el-input v-model="form.api_key" type="password" show-password />
        </el-form-item>
        <div class="grid">
          <el-form-item label="每日调用上限">
            <el-input-number v-model="form.max_calls_per_day" :min="1" :max="10000" />
          </el-form-item>
          <el-form-item label="超时（秒）">
            <el-input-number v-model="form.timeout_seconds" :min="5" :max="300" />
          </el-form-item>
          <el-form-item label="允许对方使用工具">
            <el-switch v-model="form.allow_tools" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.is_active" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
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
const testingId = ref('')
const peers = ref([])
const invocations = ref([])
const dialog = ref(false)
const form = reactive({
  id: '', name: '', description: '', endpoint: '', api_key: '', remote_name: '',
  direction: 'outbound', protocol: 'lite', allow_tools: false,
  max_calls_per_day: 50, timeout_seconds: 120, is_active: true
})

function resetForm() {
  Object.assign(form, {
    id: '', name: '', description: '', endpoint: '', api_key: '', remote_name: '',
    direction: 'outbound', protocol: 'lite', allow_tools: false,
    max_calls_per_day: 50, timeout_seconds: 120, is_active: true
  })
}

async function load() {
  loading.value = true
  try {
    peers.value = await api.get('/agent/a2a/peers')
    invocations.value = await api.get('/agent/a2a/invocations')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  dialog.value = true
}
function openEdit(row) {
  Object.assign(form, {
    ...row,
    api_key: '',
    max_calls_per_day: row.max_calls_per_day || 50,
    timeout_seconds: row.timeout_seconds || 120
  })
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.error('名称不能为空')
  saving.value = true
  try {
    const data = await api.post('/agent/a2a/peers', { ...form })
    dialog.value = false
    await load()
    if (data.api_key_plaintext) {
      await ElMessageBox.alert(data.api_key_plaintext, 'API Key（只显示一次，请复制给对方）', {
        confirmButtonText: '我已保存'
      })
    } else {
      ElMessage.success('已保存')
    }
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除伙伴「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/a2a/peers/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* ignore */
  }
}

async function reveal(row) {
  try {
    const data = await api.get(`/agent/a2a/peers/${row.id}/key`)
    await ElMessageBox.alert(data.api_key, `「${row.name}」的 API Key`, {
      confirmButtonText: '关闭'
    })
  } catch {
    /* ignore */
  }
}

async function rotate(row) {
  try {
    await ElMessageBox.confirm('重置后旧 Key 立即失效，确定？', '重置密钥', { type: 'warning' })
  } catch {
    return
  }
  try {
    const data = await api.post(`/agent/a2a/peers/${row.id}/rotate`)
    await ElMessageBox.alert(data.api_key, '新 API Key（只显示一次）', {
      confirmButtonText: '我已保存'
    })
    await load()
  } catch {
    /* ignore */
  }
}

async function testPeer(row) {
  testingId.value = row.id
  try {
    const data = await api.post(`/agent/a2a/peers/${row.id}/test`)
    ElMessage.success(`连接成功：${data.response?.data?.name || row.name}`)
  } catch {
    /* ignore */
  } finally {
    testingId.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0 18px; }
.section-title { margin: 0 0 12px; font-size: 15px; }
</style>
