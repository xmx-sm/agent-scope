<template>
  <div class="page">
    <h2 class="page-title">Agent 配置</h2>
    <p class="page-desc">大模型与 Embedding 配置独立于系统设置，支持厂商预设、自定义地址与在线获取模型</p>

    <div v-loading="loading">
      <el-tabs v-model="activeTab" class="agent-tabs">
        <el-tab-pane label="对话模型" name="chat">
          <div class="panel">
            <h3 class="card-title">模型服务</h3>
            <el-form label-position="top">
              <div class="form-grid">
                <el-form-item label="模型厂商">
                  <el-select
                    v-model="form['ai.provider']"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入厂商"
                    style="width: 100%"
                    @change="onProviderChange('chat')"
                  >
                    <el-option
                      v-for="item in providers"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="API 地址">
                  <el-input v-model="form['ai.base_url']" placeholder="https://.../v1" />
                </el-form-item>
                <el-form-item label="API Key">
                  <el-input v-model="form['ai.api_key']" type="password" show-password placeholder="sk-..." />
                </el-form-item>
                <el-form-item label="模型">
                  <div class="model-row">
                    <el-select
                      v-model="form['ai.model']"
                      filterable
                      allow-create
                      default-first-option
                      placeholder="点击右侧获取模型或手动填写"
                      style="flex: 1"
                    >
                      <el-option v-for="name in chatModels" :key="name" :label="name" :value="name" />
                    </el-select>
                    <el-button :loading="fetchingChat" @click="fetchModels('chat')">获取模型</el-button>
                  </div>
                </el-form-item>
              </div>
            </el-form>
          </div>

          <div class="panel">
            <h3 class="card-title">生成参数</h3>
            <div class="form-grid">
              <div v-for="item in genericItems('对话模型')" :key="item.key" class="field">
                <div class="field-label">{{ item.label }}</div>
                <div class="field-desc muted">{{ item.description }}</div>
                <ConfigControl :item="item" v-model="form[item.key]" />
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="向量模型" name="embedding">
          <div class="panel">
            <h3 class="card-title">Embedding 服务</h3>
            <el-form label-position="top">
              <div class="form-grid">
                <el-form-item label="模型厂商">
                  <el-select
                    v-model="form['ai.embedding.provider']"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入厂商"
                    style="width: 100%"
                    @change="onProviderChange('embedding')"
                  >
                    <el-option
                      v-for="item in providers"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="API 地址">
                  <el-input v-model="form['ai.embedding.base_url']" placeholder="https://.../v1" />
                </el-form-item>
                <el-form-item label="API Key">
                  <el-input
                    v-model="form['ai.embedding.api_key']"
                    type="password"
                    show-password
                    placeholder="sk-..."
                  />
                </el-form-item>
                <el-form-item label="Embedding 模型">
                  <div class="model-row">
                    <el-select
                      v-model="form['ai.embedding.model']"
                      filterable
                      allow-create
                      default-first-option
                      placeholder="点击右侧获取模型或手动填写"
                      style="flex: 1"
                    >
                      <el-option v-for="name in embeddingModels" :key="name" :label="name" :value="name" />
                    </el-select>
                    <el-button :loading="fetchingEmbedding" @click="fetchModels('embedding')">
                      获取模型
                    </el-button>
                  </div>
                </el-form-item>
              </div>
            </el-form>
          </div>

          <div class="panel">
            <h3 class="card-title">向量参数</h3>
            <div class="form-grid">
              <div v-for="item in genericItems('向量模型')" :key="item.key" class="field">
                <div class="field-label">{{ item.label }}</div>
                <div class="field-desc muted">{{ item.description }}</div>
                <ConfigControl :item="item" v-model="form[item.key]" />
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="Scope 默认" name="scope">
          <div class="panel">
            <h3 class="card-title">Scope 默认配置</h3>
            <p class="muted">与 scope/config/schema.py 同名对齐，供 Agent 运行时读取</p>
            <div class="form-grid">
              <div v-for="item in genericItems('Scope')" :key="item.key" class="field">
                <div class="field-label">{{ item.label }}</div>
                <div class="field-desc muted">{{ item.description }}</div>
                <ConfigControl :item="item" v-model="form[item.key]" />
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <div class="save-bar">
        <el-button type="primary" :loading="saving" @click="save">保存 Agent 配置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElInput, ElInputNumber, ElOption, ElSelect, ElSwitch, ElMessage } from 'element-plus'
import api from '../../utils/api'

const ConfigControl = defineComponent({
  name: 'ConfigControl',
  props: { item: Object, modelValue: [String, Number, Boolean] },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => {
      const value = props.modelValue
      const update = (val) => emit('update:modelValue', val)
      if (props.item.value_type === 'bool') {
        return h(ElSwitch, { modelValue: value, 'onUpdate:modelValue': update })
      }
      if (['int', 'float'].includes(props.item.value_type)) {
        return h(ElInputNumber, {
          modelValue: value,
          min: 0,
          step: props.item.value_type === 'float' ? 0.1 : 1,
          precision: props.item.value_type === 'float' ? 2 : 0,
          controlsPosition: 'right',
          'onUpdate:modelValue': update,
          style: 'width: 180px'
        })
      }
      if (props.item.secret) {
        return h(ElInput, {
          modelValue: value,
          type: 'password',
          showPassword: true,
          'onUpdate:modelValue': update
        })
      }
      if (props.item.key === 'default_role') {
        return h(ElSelect, { modelValue: value, 'onUpdate:modelValue': update }, () => [
          h(ElOption, { label: '普通用户', value: 'user' }),
          h(ElOption, { label: '管理员', value: 'admin' })
        ])
      }
      return h(ElInput, { modelValue: value, 'onUpdate:modelValue': update })
    }
  }
})

const activeTab = ref('chat')
const loading = ref(false)
const saving = ref(false)
const fetchingChat = ref(false)
const fetchingEmbedding = ref(false)
const items = ref([])
const providers = ref([])
const chatModels = ref([])
const embeddingModels = ref([])
const form = reactive({})

const CHAT_SPECIAL = ['ai.provider', 'ai.base_url', 'ai.api_key', 'ai.model']
const EMBEDDING_SPECIAL = [
  'ai.embedding.provider',
  'ai.embedding.base_url',
  'ai.embedding.api_key',
  'ai.embedding.model'
]

function genericItems(group) {
  const special = group === '对话模型' ? CHAT_SPECIAL : group === '向量模型' ? EMBEDDING_SPECIAL : []
  return items.value.filter((item) => item.group === group && !special.includes(item.key))
}

function onProviderChange(kind) {
  const providerKey = kind === 'chat' ? 'ai.provider' : 'ai.embedding.provider'
  const baseUrlKey = kind === 'chat' ? 'ai.base_url' : 'ai.embedding.base_url'
  const provider = providers.value.find((item) => item.value === form[providerKey])
  if (provider && provider.base_url) {
    form[baseUrlKey] = provider.base_url
  }
  if (kind === 'chat') chatModels.value = []
  else embeddingModels.value = []
}

async function fetchModels(kind) {
  const isChat = kind === 'chat'
  const flag = isChat ? fetchingChat : fetchingEmbedding
  flag.value = true
  try {
    const data = await api.post('/admin/agent/models', {
      provider: form[isChat ? 'ai.provider' : 'ai.embedding.provider'] || '',
      base_url: form[isChat ? 'ai.base_url' : 'ai.embedding.base_url'] || '',
      api_key: form[isChat ? 'ai.api_key' : 'ai.embedding.api_key'] || '',
      key_config: isChat ? 'ai.api_key' : 'ai.embedding.api_key'
    })
    if (isChat) chatModels.value = data.models
    else embeddingModels.value = data.models
    ElMessage.success(`获取到 ${data.models.length} 个模型`)
  } catch {
    /* ignore */
  } finally {
    flag.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const [configs, providerList] = await Promise.all([
      api.get('/admin/configs', { params: { domain: 'agent' } }),
      api.get('/admin/agent/providers')
    ])
    items.value = configs
    providers.value = providerList
    for (const item of configs) form[item.key] = item.value
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    for (const item of items.value) {
      if (item.secret && form[item.key] === '******') continue
      if (form[item.key] === item.value) continue
      await api.put(`/admin/configs/${item.key}`, { value: form[item.key] })
    }
    ElMessage.success('Agent 配置已保存')
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-title {
  margin: 0 0 14px;
  font-size: 15px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px 20px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}

.field-desc {
  font-size: 12px;
  margin-bottom: 8px;
  min-height: 16px;
}

.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.save-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.agent-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}
</style>
