<template>
  <div class="page">
    <h2 class="page-title">MCP</h2>
    <p class="page-desc">配置外部 MCP 服务，启用后会自动挂载到 Agent</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加 MCP</el-button>
      </div>

      <el-table :data="mcps" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column prop="mcp_type" label="类型" width="90" />
        <el-table-column label="地址 / 命令" min-width="220">
          <template #default="{ row }">{{ row.mcp_type === 'http' ? row.url : row.command }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" @change="(checked) => toggle(row, checked)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!mcps.length && !loading" description="暂无 MCP" :image-size="70" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑 MCP' : '添加 MCP'" :width="isMobile ? '94%' : '560px'">
      <el-form :model="form" label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.mcp_type">
            <el-radio-button value="http">HTTP</el-radio-button>
            <el-radio-button value="stdio">stdio</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.mcp_type === 'http'" label="URL">
          <el-input v-model="form.url" placeholder="https://..." />
        </el-form-item>
        <template v-else>
          <el-form-item label="命令"><el-input v-model="form.command" placeholder="npx" /></el-form-item>
          <el-form-item label="参数（JSON 数组）">
            <el-input v-model="argsText" type="textarea" :rows="3" placeholder='["-y","@modelcontextprotocol/server-filesystem","/tmp"]' />
          </el-form-item>
          <el-form-item label="环境变量（JSON 对象）">
            <el-input v-model="envText" type="textarea" :rows="3" placeholder='{"KEY":"value"}' />
          </el-form-item>
        </template>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const saving = ref(false)
const mcps = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = reactive(emptyForm())
const argsText = ref('[]')
const envText = ref('{}')

function emptyForm() {
  return { id: '', name: '', mcp_type: 'http', url: '', command: '', is_active: true }
}

async function load() {
  loading.value = true
  try {
    mcps.value = await api.get('/agent/mcps')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  Object.assign(form, emptyForm())
  argsText.value = '[]'
  envText.value = '{}'
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = true
  Object.assign(form, {
    id: row.id,
    name: row.name,
    mcp_type: row.mcp_type,
    url: row.url,
    command: row.command,
    is_active: row.is_active
  })
  argsText.value = JSON.stringify(row.args || [], null, 2)
  envText.value = JSON.stringify(row.env || {}, null, 2)
  dialogVisible.value = true
}

async function save() {
  let args = []
  let env = {}
  try {
    args = JSON.parse(argsText.value || '[]')
    env = JSON.parse(envText.value || '{}')
  } catch {
    ElMessage.error('参数或环境变量不是合法 JSON')
    return
  }
  saving.value = true
  try {
    await api.post('/agent/mcps', { ...form, args, env })
    ElMessage.success('MCP 已保存')
    dialogVisible.value = false
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function toggle(row, checked) {
  try {
    await api.post('/agent/mcps', { ...row, is_active: checked })
    row.is_active = checked
  } catch {
    /* ignore */
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除 MCP「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/mcps/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
