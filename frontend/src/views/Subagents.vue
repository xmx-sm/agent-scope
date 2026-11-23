<template>
  <div :class="embedded ? 'embedded-panel' : 'page'">
    <template v-if="!embedded">
      <h2 class="page-title">子智能体</h2>
      <p class="page-desc">为 Agent 配置可委派的子智能体；主 Agent 会通过委派工具调用它们</p>
    </template>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增子智能体</el-button>
      </div>

      <el-table :data="items" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column label="模型" min-width="140">
          <template #default="{ row }">
            <span>{{ row.llm_config?.model || '跟随个人配置' }}</span>
          </template>
        </el-table-column>
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
        <el-divider content-position="left">模型覆盖（留空跟随个人 Agent 配置）</el-divider>
        <div class="form-grid">
          <el-form-item label="服务商">
            <el-input v-model="form.llm_config.provider" placeholder="openai-compatible" />
          </el-form-item>
          <el-form-item label="模型">
            <el-input v-model="form.llm_config.model" placeholder="gpt-4o-mini" />
          </el-form-item>
          <el-form-item label="API 地址">
            <el-input v-model="form.llm_config.base_url" placeholder="https://.../v1" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="form.llm_config.api_key" type="password" show-password />
          </el-form-item>
          <el-form-item label="温度">
            <el-input-number v-model="form.llm_config.temperature" :min="0" :max="2" :step="0.1" />
          </el-form-item>
          <el-form-item label="最大输出 tokens">
            <el-input-number v-model="form.llm_config.max_tokens" :min="64" :step="256" />
          </el-form-item>
          <el-form-item label="思考强度">
            <el-select v-model="form.llm_config.reasoning_effort" clearable style="width: 100%">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
            </el-select>
          </el-form-item>
        </div>
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

defineProps({
  embedded: { type: Boolean, default: false }
})

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const saving = ref(false)
const items = ref([])
const toolOptions = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = reactive(emptyForm())

function blankLlm() {
  return {
    provider: '',
    model: '',
    base_url: '',
    api_key: '',
    temperature: null,
    max_tokens: null,
    reasoning_effort: ''
  }
}

function emptyForm() {
  return {
    id: '',
    name: '',
    description: '',
    system_prompt: '',
    llm_config: blankLlm(),
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
    llm_config: { ...blankLlm(), ...(row.llm_config || {}) },
    tools: [...(row.tools || [])],
    mode: row.mode,
    is_active: row.is_active
  })
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    const llm = {}
    Object.entries(form.llm_config || {}).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) llm[key] = value
    })
    await api.post('/agent/subagents', { ...form, llm_config: llm })
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

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 18px;
}
</style>
