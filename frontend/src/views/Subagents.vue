<template>
  <div class="page">
    <h2 class="page-title">子智能体</h2>
    <p class="page-desc">为 Agent 配置可委派的子智能体；主 Agent 会通过委派工具调用它们</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增子智能体</el-button>
      </div>

      <el-table :data="items" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column label="工具" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="tool in row.tools" :key="tool" size="small" effect="plain" class="tool-tag">
              {{ tool }}
            </el-tag>
            <span v-if="!row.tools.length" class="muted">无</span>
          </template>
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
      <el-empty v-if="!items.length && !loading" description="暂无子智能体" :image-size="70" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑子智能体' : '新增子智能体'" :width="isMobile ? '94%' : '620px'">
      <el-form :model="form" label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" placeholder="主 Agent 据此判断何时委派" /></el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="form.system_prompt" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="可用工具">
          <el-select v-model="form.tools" multiple filterable style="width: 100%">
            <el-option v-for="tool in toolOptions" :key="tool.name" :label="`${tool.label}（${tool.name}）`" :value="tool.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行模式">
          <el-select v-model="form.mode" style="width: 100%">
            <el-option label="自动" value="auto" />
            <el-option label="黑盒" value="blackbox" />
            <el-option label="透明" value="transparent" />
          </el-select>
        </el-form-item>
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
const items = ref([])
const toolOptions = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = reactive(emptyForm())

function emptyForm() {
  return {
    id: '',
    name: '',
    description: '',
    system_prompt: '',
    tools: [],
    mode: 'auto',
    is_active: true
  }
}

async function load() {
  loading.value = true
  try {
    const [list, catalog] = await Promise.all([
      api.get('/agent/subagents'),
      api.get('/tools/catalog')
    ])
    items.value = list
    toolOptions.value = catalog.flatMap((group) => group.tools || [])
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = true
  Object.assign(form, {
    id: row.id,
    name: row.name,
    description: row.description,
    system_prompt: row.system_prompt,
    tools: [...(row.tools || [])],
    mode: row.mode,
    is_active: row.is_active
  })
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    await api.post('/agent/subagents', { ...form })
    ElMessage.success('子智能体已保存')
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
    await api.post('/agent/subagents', { ...row, is_active: checked })
    row.is_active = checked
  } catch {
    /* ignore */
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除子智能体「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/subagents/${row.id}`)
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

.tool-tag {
  margin-right: 4px;
}
</style>
