<template>
  <div :class="embedded ? 'embedded-panel' : 'page'">
    <div class="page-head">
      <div v-if="!embedded">
        <h2 class="page-title">超级智能体</h2>
        <p class="page-desc">一个主智能体负责编排，多个子智能体可长期独立对话；每个成员可覆盖模型与提示词。</p>
      </div>
      <div v-else class="grow"></div>
      <el-button v-if="form.id" type="primary" :loading="entering" @click="enterMain">进入主对话</el-button>
    </div>

    <div v-loading="loading" class="panel">
      <el-form label-position="top">
        <div class="grid">
          <el-form-item label="名称">
            <el-input v-model="form.name" placeholder="超级智能体" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
        </div>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="这个超级智能体负责什么" />
        </el-form-item>
      </el-form>

      <el-divider content-position="left">主智能体</el-divider>
      <MemberForm :member="form.main" role="main" />

      <el-divider content-position="left">
        子智能体（{{ form.subs.length }}）
        <el-button class="add-sub" size="small" type="primary" plain @click="addSub">添加子智能体</el-button>
      </el-divider>
      <el-collapse v-if="form.subs.length" v-model="openSubs">
        <el-collapse-item
          v-for="(member, index) in form.subs"
          :key="member._key"
          :name="member._key"
        >
          <template #title>
            <span class="sub-title">{{ member.name || `子智能体 ${index + 1}` }}</span>
            <el-tag v-if="member.is_active === false" size="small" type="info">停用</el-tag>
          </template>
          <MemberForm :member="member" role="sub" @remove="removeSub(index)" />
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="暂无子智能体" :image-size="60" />

      <div class="actions">
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
        <el-button v-if="form.id" type="danger" plain @click="remove">删除</el-button>
      </div>
    </div>

    <div v-if="form.id" class="panel records">
      <div class="records-head">
        <h3 class="records-title">会话记录</h3>
        <el-button size="small" @click="openAllRecords">在对话页查看</el-button>
      </div>
      <el-table :data="conversationRows" size="small" stripe>
        <el-table-column prop="title" label="会话" min-width="220" show-overflow-tooltip />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ originLabel(row.origin) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="openConversation(row)">打开</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!conversationRows.length" description="暂无会话记录" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElButton, ElCollapse, ElCollapseItem, ElDivider, ElEmpty, ElForm, ElFormItem, ElInput, ElInputNumber, ElMessage, ElMessageBox, ElOption, ElSelect, ElSwitch, ElTag } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '../utils/api'

defineProps({
  embedded: { type: Boolean, default: false }
})

function blankLlM() {
  return {
    provider: '', base_url: '', api_key: '', model: '',
    temperature: null, max_tokens: null, reasoning_effort: ''
  }
}
function blankMember(role = 'sub') {
  return {
    _key: `${Date.now()}-${Math.random()}`,
    id: '', role, name: '', description: '', system_prompt: '',
    llm_config: blankLlM(), sort_order: role === 'main' ? 0 : 1, is_active: true
  }
}
function normalizeMember(raw, role) {
  return {
    ...blankMember(role),
    ...(raw || {}),
    _key: raw?.id || `${Date.now()}-${Math.random()}`,
    llm_config: { ...blankLlM(), ...(raw?.llm_config || {}) }
  }
}

const MemberForm = defineComponent({
  props: { member: { type: Object, required: true }, role: { type: String, default: 'sub' } },
  emits: ['remove'],
  setup(props, { emit }) {
    return () => h('div', { class: 'member-form' }, [
      h('div', { class: 'grid' }, [
        h(ElFormItem, { label: '名称' }, () => h(ElInput, {
          modelValue: props.member.name,
          'onUpdate:modelValue': (v) => (props.member.name = v),
          placeholder: props.role === 'main' ? '主智能体' : '子智能体'
        })),
        h(ElFormItem, { label: '状态' }, () => h(ElSwitch, {
          modelValue: props.member.is_active !== false,
          'onUpdate:modelValue': (v) => (props.member.is_active = v)
        }))
      ]),
      h(ElFormItem, { label: '职责描述' }, () => h(ElInput, {
        modelValue: props.member.description,
        'onUpdate:modelValue': (v) => (props.member.description = v),
        placeholder: '给主智能体编排时看的能力说明'
      })),
      h(ElFormItem, { label: '系统提示词' }, () => h(ElInput, {
        modelValue: props.member.system_prompt,
        'onUpdate:modelValue': (v) => (props.member.system_prompt = v),
        type: 'textarea', rows: 4,
        placeholder: props.role === 'main' ? '定义编排规则、何时创建子会话' : '定义该子智能体的专业能力'
      })),
      h(ElDivider, { contentPosition: 'left' }, () => '模型覆盖（留空跟随个人 Agent 配置）'),
      h('div', { class: 'grid' }, [
        h(ElFormItem, { label: '服务商' }, () => h(ElInput, {
          modelValue: props.member.llm_config.provider,
          'onUpdate:modelValue': (v) => (props.member.llm_config.provider = v),
          placeholder: 'openai-compatible'
        })),
        h(ElFormItem, { label: '模型' }, () => h(ElInput, {
          modelValue: props.member.llm_config.model,
          'onUpdate:modelValue': (v) => (props.member.llm_config.model = v)
        })),
        h(ElFormItem, { label: 'API 地址' }, () => h(ElInput, {
          modelValue: props.member.llm_config.base_url,
          'onUpdate:modelValue': (v) => (props.member.llm_config.base_url = v)
        })),
        h(ElFormItem, { label: 'API Key' }, () => h(ElInput, {
          modelValue: props.member.llm_config.api_key,
          'onUpdate:modelValue': (v) => (props.member.llm_config.api_key = v),
          type: 'password', showPassword: true
        })),
        h(ElFormItem, { label: '温度' }, () => h(ElInputNumber, {
          modelValue: props.member.llm_config.temperature,
          'onUpdate:modelValue': (v) => (props.member.llm_config.temperature = v),
          min: 0, max: 2, step: 0.1
        })),
        h(ElFormItem, { label: '思考强度' }, () => h(ElSelect, {
          modelValue: props.member.llm_config.reasoning_effort,
          'onUpdate:modelValue': (v) => (props.member.llm_config.reasoning_effort = v),
          clearable: true, style: 'width:100%'
        }, () => ['low', 'medium', 'high'].map((item) => h(ElOption, { label: item, value: item }))))
      ]),
      props.role === 'sub'
        ? h('div', { class: 'member-actions' }, [
            h(ElButton, { type: 'danger', plain: true, size: 'small', onClick: () => emit('remove') }, () => '移除此成员')
          ])
        : null
    ])
  }
})

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const entering = ref(false)
const openSubs = ref([])
const form = reactive({
  id: '', name: '超级智能体', description: '', enabled: false,
  main: blankMember('main'), subs: []
})
const conversationRows = ref([])

const ORIGIN_LABELS = { super_main: '超级·主', super_sub: '超级·子' }

function originLabel(origin) {
  return ORIGIN_LABELS[origin] || origin || '会话'
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

async function loadSuperConversations() {
  if (!form.id) {
    conversationRows.value = []
    return
  }
  try {
    conversationRows.value = await api.get('/agent/conversations', {
      params: { super_agent_id: form.id, limit: 100 }
    })
  } catch {
    conversationRows.value = []
  }
}

function openConversation(row) {
  router.push({ path: '/chat', query: { conversation: row.id, origin: 'super' } })
}

function openAllRecords() {
  router.push({ path: '/chat', query: { origin: 'super' } })
}

function apply(data) {
  if (!data) {
    Object.assign(form, { id: '', name: '超级智能体', description: '', enabled: false, main: blankMember('main'), subs: [] })
    return
  }
  Object.assign(form, {
    id: data.id,
    name: data.name,
    description: data.description || '',
    enabled: Boolean(data.enabled),
    main: normalizeMember(data.main, 'main'),
    subs: (data.subs || []).map((item) => normalizeMember(item, 'sub'))
  })
  openSubs.value = form.subs.map((item) => item._key)
}

async function load() {
  loading.value = true
  try {
    apply(await api.get('/agent/super-agent'))
    await loadSuperConversations()
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function addSub() {
  const member = blankMember('sub')
  form.subs.push(member)
  openSubs.value.push(member._key)
}
function removeSub(index) {
  form.subs.splice(index, 1)
}

function payloadMember(member) {
  const llm = {}
  Object.entries(member.llm_config || {}).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) llm[key] = value
  })
  const out = {
    id: member.id || undefined,
    role: member.role,
    name: member.name,
    description: member.description,
    system_prompt: member.system_prompt,
    llm_config: llm,
    sort_order: member.sort_order,
    is_active: member.is_active !== false
  }
  return out
}

async function save() {
  if (!form.main.name.trim()) return ElMessage.error('主智能体名称不能为空')
  if (!form.main.system_prompt.trim()) return ElMessage.error('主智能体提示词不能为空')
  saving.value = true
  try {
    const data = await api.post('/agent/super-agent', {
      id: form.id || undefined,
      name: form.name,
      description: form.description,
      enabled: form.enabled,
      main: payloadMember(form.main),
      subs: form.subs.map(payloadMember)
    })
    apply(data)
    await loadSuperConversations()
    ElMessage.success('已保存')
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function enterMain() {
  entering.value = true
  try {
    const conv = await api.post('/agent/super-agent/main-conversation', {
      super_agent_id: form.id,
      role: 'main'
    })
    router.push({ path: '/chat', query: { conversation: conv.id } })
  } catch {
    /* ignore */
  } finally {
    entering.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm('删除超级智能体配置？已创建的历史会话会保留。', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete('/agent/super-agent', { params: { super_agent_id: form.id } })
    apply(null)
    conversationRows.value = []
    ElMessage.success('已删除')
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0 18px; }
.member-form { padding: 2px 0 8px; }
.member-actions { margin-top: 4px; }
.sub-title { margin-right: 10px; font-weight: 600; }
.add-sub { margin-left: 10px; }
.actions { display: flex; gap: 10px; margin-top: 18px; }
.records { margin-top: 16px; }
.records-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.records-title { margin: 0; font-size: 15px; }
</style>
