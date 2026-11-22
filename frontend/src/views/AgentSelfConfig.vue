<template>
  <div class="page">
    <h2 class="page-title">Agent 设置</h2>
    <p class="page-desc">默认跟随系统 Agent 配置；也可以为自己的账号单独设置模型与提示词</p>

    <div class="panel" v-loading="loading">
      <el-radio-group v-model="useDefault" class="mode-switch">
        <el-radio-button :value="true">跟随系统默认</el-radio-button>
        <el-radio-button :value="false">自定义配置</el-radio-button>
      </el-radio-group>

      <div v-if="useDefault" class="system-info">
        <p class="muted">当前使用系统默认配置：</p>
        <div class="info-grid">
          <div><span class="muted">模型</span><b>{{ view.system.model || '未配置' }}</b></div>
          <div><span class="muted">地址</span><b>{{ view.system.base_url || '未配置' }}</b></div>
          <div><span class="muted">Key</span><b>{{ view.system.api_key || '未配置' }}</b></div>
          <div><span class="muted">温度</span><b>{{ view.system.temperature }}</b></div>
        </div>
      </div>

      <el-form v-else label-position="top" class="config-form">
        <div class="form-grid">
          <el-form-item label="模型厂商">
            <el-select v-model="form.provider" filterable allow-create default-first-option style="width: 100%">
              <el-option v-for="item in providers" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="API 地址">
            <el-input v-model="form.base_url" placeholder="https://.../v1" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
          </el-form-item>
          <el-form-item label="模型">
            <div class="model-row">
              <el-select v-model="form.model" filterable allow-create default-first-option style="flex: 1">
                <el-option v-for="name in models" :key="name" :label="name" :value="name" />
              </el-select>
              <el-button :loading="fetching" @click="fetchModels">获取模型</el-button>
            </div>
          </el-form-item>
          <el-form-item label="温度">
            <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :precision="2" />
          </el-form-item>
          <el-form-item label="最大输出 tokens">
            <el-input-number v-model="form.max_tokens" :min="64" :step="256" />
          </el-form-item>
          <el-form-item label="上下文窗口">
            <el-input-number v-model="form.context_window" :min="1024" :step="1024" />
          </el-form-item>
          <el-form-item label="流式输出">
            <el-switch v-model="form.stream" />
          </el-form-item>
          <el-form-item label="思考模式">
            <el-switch v-model="form.think" />
          </el-form-item>
          <el-form-item label="思考预算 tokens">
            <el-input-number v-model="form.thinking_budget" :min="0" :step="256" />
          </el-form-item>
          <el-form-item label="思考强度">
            <el-select v-model="form.reasoning_effort" style="width: 100%">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="系统提示词">
          <el-input v-model="form.system_prompt" type="textarea" :rows="5" placeholder="留空使用系统默认提示词" />
        </el-form-item>
      </el-form>

      <div class="save-bar">
        <el-button @click="reset" :loading="resetting">恢复系统默认</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const loading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const fetching = ref(false)
const useDefault = ref(true)
const view = ref({ system: {}, user: {}, effective: {} })
const providers = ref([])
const models = ref([])
const form = reactive({
  provider: 'openai-compatible',
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
  max_tokens: 4096,
  context_window: 131072,
  stream: true,
  think: false,
  thinking_budget: 0,
  reasoning_effort: 'medium',
  system_prompt: ''
})

async function load() {
  loading.value = true
  try {
    const [config, providerList] = await Promise.all([
      api.get('/agent/config'),
      api.get('/agent/providers').catch(() => [])
    ])
    view.value = config
    useDefault.value = config.use_system_default
    Object.assign(form, {
      provider: config.user.provider || config.system.provider || 'openai-compatible',
      base_url: config.user.base_url || '',
      api_key: config.user.api_key || '',
      model: config.user.model || '',
      temperature: config.user.temperature ?? config.system.temperature ?? 0.7,
      max_tokens: config.user.max_tokens ?? config.system.max_tokens ?? 4096,
      context_window: config.user.context_window ?? config.system.context_window ?? 131072,
      stream: config.user.stream ?? config.system.stream ?? true,
      think: config.user.think ?? config.system.think ?? false,
      thinking_budget: config.user.thinking_budget ?? config.system.thinking_budget ?? 0,
      reasoning_effort: config.user.reasoning_effort || config.system.reasoning_effort || 'medium',
      system_prompt: config.user.system_prompt || ''
    })
    providers.value = providerList || []
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function fetchModels() {
  fetching.value = true
  try {
    const data = await api.post('/agent/models', {
      provider: form.provider,
      base_url: form.base_url,
      api_key: form.api_key
    })
    models.value = data.models
    ElMessage.success(`获取到 ${data.models.length} 个模型`)
  } catch {
    /* ignore */
  } finally {
    fetching.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const data = await api.put('/agent/config', { ...form, use_system_default: useDefault.value })
    view.value = data
    ElMessage.success('Agent 配置已保存')
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function reset() {
  resetting.value = true
  try {
    view.value = await api.delete('/agent/config')
    useDefault.value = true
    ElMessage.success('已恢复跟随系统默认')
    await load()
  } catch {
    /* ignore */
  } finally {
    resetting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mode-switch {
  margin-bottom: 16px;
}

.system-info {
  background: #f8fafc;
  border-radius: 10px;
  padding: 14px;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 10px;
  font-size: 13px;
}

.info-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 20px;
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
  gap: 8px;
}
</style>
