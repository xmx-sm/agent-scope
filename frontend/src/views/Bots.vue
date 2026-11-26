<template>
  <div class="page">
    <div class="page-heading">
      <div>
        <h2 class="page-title">机器人</h2>
        <p class="page-desc">创建第三方机器人接入，通过 Webhook 调用你的 Agent</p>
      </div>
      <div>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新建机器人</el-button>
      </div>
    </div>

    <el-alert
      class="notice"
      type="info"
      :closable="false"
      title="平台支持"
      description="首期支持通用 Webhook；QQ、微信、钉钉适配器正在规划中，暂不能创建启用。"
    />

    <el-table v-loading="loading" :data="bots" row-key="id" style="margin-top: 14px">
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="平台" width="130">
        <template #default="{ row }">
          <el-tag>{{ platformLabel(row.platform) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '已启用' : '已停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="AI 工具" width="110">
        <template #default="{ row }">
          <el-tag :type="row.tools_enabled ? 'warning' : 'info'">{{ row.tools_enabled ? '允许' : '关闭' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="timeout_seconds" label="超时（秒）" width="110" />
      <el-table-column label="Webhook" min-width="260">
        <template #default="{ row }">
          <el-button link type="primary" @click="showEndpoint(row)">查看接入地址</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button link :type="row.enabled ? 'warning' : 'success'" @click="toggle(row)">
            {{ row.enabled ? '停用' : '启用' }}
          </el-button>
          <el-button link @click="rotate(row)">轮换密钥</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="新建机器人" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="100" placeholder="例如：CRM 客服机器人" />
        </el-form-item>
        <el-form-item label="平台" prop="platform">
          <el-select v-model="form.platform" style="width: 100%">
            <el-option label="通用 Webhook" value="webhook" />
            <el-option label="QQ（规划中）" value="qq" disabled />
            <el-option label="微信（规划中）" value="wechat" disabled />
            <el-option label="钉钉（规划中）" value="dingtalk" disabled />
          </el-select>
        </el-form-item>
        <el-form-item label="允许 AI 工具">
          <el-switch v-model="form.tools_enabled" />
          <span class="muted field-hint">默认关闭，开启后 Agent 可按你的权限调用工具</span>
        </el-form-item>
        <el-form-item label="处理超时">
          <el-input-number v-model="form.timeout_seconds" :min="5" :max="600" />
          <span class="muted field-hint">秒</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="credentialVisible" title="接入信息" width="620px">
      <el-alert v-if="credentialSecret" type="warning" :closable="false" title="密钥只显示一次" description="请立即复制并保存，关闭后无法再次查看。" />
      <div class="credential-block">
        <div class="credential-label">Webhook 地址</div>
        <el-input :model-value="credentialUrl" readonly>
          <template #append><el-button @click="copy(credentialUrl)">复制</el-button></template>
        </el-input>
      </div>
      <div v-if="credentialSecret" class="credential-block">
        <div class="credential-label">签名密钥</div>
        <el-input :model-value="credentialSecret" readonly>
          <template #append><el-button @click="copy(credentialSecret)">复制</el-button></template>
        </el-input>
      </div>
      <div class="credential-block">
        <div class="credential-label">请求格式</div>
        <p class="muted field-hint">签名：HMAC-SHA256(secret, timestamp + "." + 原始请求体)，通过 X-Webhook-Signature 传入。</p>
        <pre class="payload-example">{{ payloadExample }}</pre>
      </div>
      <template #footer><el-button type="primary" @click="credentialVisible = false">我已保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../utils/api'

const bots = ref([])
const loading = ref(false)
const creating = ref(false)
const createVisible = ref(false)
const credentialVisible = ref(false)
const formRef = ref()
const credentialUrl = ref('')
const credentialSecret = ref('')
const form = reactive({ name: '', platform: 'webhook', tools_enabled: false, timeout_seconds: 120 })
const rules = { name: [{ required: true, message: '请输入机器人名称', trigger: 'blur' }] }

const payloadExample = computed(() => JSON.stringify({
  event_id: 'unique-event-id',
  sender_id: 'user-123',
  chat_id: 'chat-123',
  chat_type: 'private',
  text: '帮我查询今天的客户跟进'
}, null, 2))

function platformLabel(platform) {
  return ({ webhook: '通用 Webhook', qq: 'QQ', wechat: '微信', dingtalk: '钉钉' })[platform] || platform
}

function webhookUrl(bot) {
  const apiBase = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`
  const base = apiBase.startsWith('http') ? apiBase : `${window.location.origin}${apiBase}`
  return `${base.replace(/\/$/, '')}/public/bots/${bot.id}/webhook`
}

async function load() {
  loading.value = true
  try {
    bots.value = await api.get('/bots')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { name: '', platform: 'webhook', tools_enabled: false, timeout_seconds: 120 })
  createVisible.value = true
}

async function create() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    const bot = await api.post('/bots', { ...form })
    bots.value.unshift(bot)
    createVisible.value = false
    credentialUrl.value = webhookUrl(bot)
    credentialSecret.value = bot.secret
    credentialVisible.value = true
  } catch {
    /* ignore */
  } finally {
    creating.value = false
  }
}

function showCredentials(bot) {
  credentialUrl.value = webhookUrl(bot)
  credentialSecret.value = bot.secret
  credentialVisible.value = true
}

function showEndpoint(bot) {
  credentialUrl.value = webhookUrl(bot)
  credentialSecret.value = ''
  credentialVisible.value = true
}

async function copy(value) {
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

async function toggle(bot) {
  try {
    const updated = await api.patch(`/bots/${bot.id}`, { enabled: !bot.enabled })
    Object.assign(bot, updated)
  } catch {
    /* ignore */
  }
}

async function rotate(bot) {
  try {
    await ElMessageBox.confirm('轮换后旧密钥会立即失效，确定继续吗？', '轮换密钥', { type: 'warning' })
  } catch {
    return
  }
  try {
    const updated = await api.post(`/bots/${bot.id}/rotate-secret`)
    Object.assign(bot, updated)
    showCredentials(updated)
  } catch {
    /* ignore */
  }
}

async function remove(bot) {
  try {
    await ElMessageBox.confirm(`确定删除机器人“${bot.name}”吗？`, '删除机器人', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/bots/${bot.id}`)
    bots.value = bots.value.filter((item) => item.id !== bot.id)
    ElMessage.success('机器人已删除')
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.notice {
  margin-top: 8px;
}

.field-hint {
  margin-left: 10px;
  font-size: 12px;
}

.credential-block {
  margin-top: 16px;
}

.credential-label {
  margin-bottom: 6px;
  font-weight: 600;
}

.payload-example {
  padding: 12px;
  border-radius: 8px;
  background: #f1f5f9;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
