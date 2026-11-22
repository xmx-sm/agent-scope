<template>
  <div class="page">
    <h2 class="page-title">定时任务</h2>
    <p class="page-desc">按间隔或日历规则，让 AI 自动在自己的会话里执行指令；结果可在对话页回看。</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <el-tag type="info" effect="plain">共 {{ jobs.length }} 个</el-tag>
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-table :data="jobs" size="small" stripe>
        <el-table-column prop="name" label="任务" min-width="130" />
        <el-table-column prop="instruction" label="指令" min-width="220" show-overflow-tooltip />
        <el-table-column label="调度" min-width="170">
          <template #default="{ row }">
            {{ row.schedule_mode === 'calendar' ? row.calendar_summary : humanInterval(row.interval_seconds) }}
          </template>
        </el-table-column>
        <el-table-column label="下次执行" width="150">
          <template #default="{ row }">
            <span :class="{ due: row.enabled && row.next_run_in <= 60 }">
              {{ row.enabled ? countdown(row) : '已停用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最近执行" width="130">
          <template #default="{ row }">
            <el-tooltip v-if="row.last_error" :content="row.last_error" placement="top">
              <el-tag size="small" :type="statusType(row.last_status)">{{ row.last_status || 'idle' }}</el-tag>
            </el-tooltip>
            <el-tag v-else size="small" :type="statusType(row.last_status)">{{ row.last_status || 'idle' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_count" label="次数" width="65" />
        <el-table-column label="会话" width="80">
          <template #default="{ row }">{{ row.conv_mode === 'fixed' ? '固定' : '每次新建' }}</template>
        </el-table-column>
        <el-table-column label="启用" width="75">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="(value) => toggle(row, value)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="runNow(row)">立即执行</el-button>
            <el-button v-if="row.last_conversation_id" link type="primary" @click="openConversation(row)">结果</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!jobs.length && !loading" description="暂无定时任务" :image-size="70" />
    </div>

    <el-dialog v-model="dialog" :title="form.id ? '编辑定时任务' : '新建定时任务'" :width="isMobile ? '94%' : '680px'">
      <el-form :model="form" label-position="top">
        <div class="grid">
          <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        </div>
        <el-form-item label="执行指令">
          <el-input v-model="form.instruction" type="textarea" :rows="4" placeholder="告诉 AI 每次要做什么" />
        </el-form-item>
        <el-form-item label="调度方式">
          <el-radio-group v-model="form.schedule_mode">
            <el-radio-button label="interval">固定间隔</el-radio-button>
            <el-radio-button label="calendar">日历规则</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.schedule_mode === 'interval'">
          <el-form-item label="执行间隔">
            <div class="inline">
              <el-input-number v-model="form.interval_value" :min="1" :max="366 * 24" />
              <el-select v-model="form.interval_unit" style="width: 100px">
                <el-option label="分钟" value="minute" />
                <el-option label="小时" value="hour" />
                <el-option label="天" value="day" />
              </el-select>
            </div>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="日期规则">
            <el-radio-group v-model="form.calendar_rule.date_mode">
              <el-radio label="weekday">每周</el-radio>
              <el-radio label="month_range">每月日号</el-radio>
              <el-radio label="date_span">日期范围</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="form.calendar_rule.date_mode === 'weekday'" label="星期">
            <el-checkbox-group v-model="form.calendar_rule.weekdays">
              <el-checkbox v-for="day in 7" :key="day" :label="day">
                {{ ['一', '二', '三', '四', '五', '六', '日'][day - 1] }}
              </el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <div v-else-if="form.calendar_rule.date_mode === 'month_range'" class="grid">
            <el-form-item label="每月起始日"><el-input-number v-model="form.calendar_rule.month_from" :min="1" :max="31" /></el-form-item>
            <el-form-item label="每月结束日"><el-input-number v-model="form.calendar_rule.month_to" :min="1" :max="31" /></el-form-item>
          </div>
          <div v-else class="grid">
            <el-form-item label="开始日期"><el-date-picker v-model="form.calendar_rule.start_date" value-format="YYYY-MM-DD" type="date" style="width:100%" /></el-form-item>
            <el-form-item label="结束日期"><el-date-picker v-model="form.calendar_rule.end_date" value-format="YYYY-MM-DD" type="date" style="width:100%" /></el-form-item>
          </div>
          <el-form-item label="每天时刻（北京时间，可输入 08:30）">
            <el-select
              v-model="form.calendar_rule.times"
              multiple
              filterable
              allow-create
              default-first-option
              style="width: 100%"
              placeholder="选择或输入时刻"
            >
              <el-option v-for="time in timeOptions" :key="time" :label="time" :value="time" />
            </el-select>
          </el-form-item>
        </template>

        <div class="grid">
          <el-form-item label="结果会话">
            <el-select v-model="form.conv_mode" style="width:100%">
              <el-option label="每次新建会话" value="new" />
              <el-option label="固定会话追加" value="fixed" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.conv_mode === 'fixed'" label="目标会话">
            <el-select v-model="form.conversation_id" filterable style="width:100%">
              <el-option v-for="conv in conversations" :key="conv.id" :label="conv.title" :value="conv.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="执行超时（秒）">
            <el-input-number v-model="form.timeout_seconds" :min="10" :max="1800" :step="30" />
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
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import api from '../utils/api'

const router = useRouter()
const isMobile = ref(window.innerWidth < 768)
const jobs = ref([])
const conversations = ref([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const now = ref(Date.now())
let timer = null
const timeOptions = Array.from({ length: 32 }, (_, i) => {
  const minutes = i * 30
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}).filter((item) => item <= '23:30')

const form = reactive({
  id: '', name: '', instruction: '', enabled: true,
  schedule_mode: 'interval', interval_value: 1, interval_unit: 'hour',
  calendar_rule: { date_mode: 'weekday', weekdays: [1, 2, 3, 4, 5], times: ['09:00'], month_from: 1, month_to: 5, start_date: '', end_date: '' },
  conv_mode: 'new', conversation_id: '', timeout_seconds: 300
})

function humanInterval(seconds) {
  const value = Number(seconds || 0)
  if (value % 86400 === 0) return `每 ${value / 86400} 天`
  if (value % 3600 === 0) return `每 ${value / 3600} 小时`
  if (value % 60 === 0) return `每 ${value / 60} 分钟`
  return `每 ${value} 秒`
}
function countdown(row) {
  if (row.next_run_at) {
    const seconds = Math.round((new Date(row.next_run_at).getTime() - now.value) / 1000)
    if (seconds <= 0) return '即将触发'
    if (seconds < 60) return `${seconds} 秒后`
    if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟后`
    if (seconds < 86400) return `${Math.ceil(seconds / 3600)} 小时后`
    return `${Math.ceil(seconds / 86400)} 天后`
  }
  return '—'
}
function statusType(status) {
  return { success: 'success', error: 'danger', timeout: 'warning', running: 'warning', idle: 'info' }[status] || 'info'
}

async function load() {
  loading.value = true
  try {
    jobs.value = await api.get('/agent/scheduled-jobs')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function loadConversations() {
  try {
    conversations.value = await api.get('/agent/conversations')
  } catch {
    conversations.value = []
  }
}

function resetForm() {
  Object.assign(form, {
    id: '', name: '', instruction: '', enabled: true,
    schedule_mode: 'interval', interval_value: 1, interval_unit: 'hour',
    calendar_rule: { date_mode: 'weekday', weekdays: [1, 2, 3, 4, 5], times: ['09:00'], month_from: 1, month_to: 5, start_date: '', end_date: '' },
    conv_mode: 'new', conversation_id: '', timeout_seconds: 300
  })
}

function openCreate() {
  resetForm()
  dialog.value = true
  loadConversations()
}
function openEdit(row) {
  const seconds = row.interval_seconds || 3600
  let value = seconds / 3600
  let unit = 'hour'
  if (seconds % 86400 === 0) {
    value = seconds / 86400
    unit = 'day'
  } else if (seconds % 3600 !== 0) {
    value = Math.max(1, Math.round(seconds / 60))
    unit = 'minute'
  }
  Object.assign(form, {
    ...row,
    interval_value: value,
    interval_unit: unit,
    calendar_rule: {
      date_mode: 'weekday', weekdays: [1, 2, 3, 4, 5], times: ['09:00'],
      month_from: 1, month_to: 5, start_date: '', end_date: '',
      ...(row.calendar_rule || {})
    }
  })
  dialog.value = true
  loadConversations()
}

function payload() {
  let interval = 3600
  if (form.schedule_mode === 'interval') {
    const unit = { minute: 60, hour: 3600, day: 86400 }[form.interval_unit] || 3600
    interval = Math.max(60, Number(form.interval_value || 1) * unit)
  }
  return {
    id: form.id || undefined,
    name: form.name,
    instruction: form.instruction,
    enabled: form.enabled,
    schedule_mode: form.schedule_mode,
    interval_seconds: interval,
    calendar_rule: form.schedule_mode === 'calendar' ? form.calendar_rule : null,
    conv_mode: form.conv_mode,
    conversation_id: form.conv_mode === 'fixed' ? form.conversation_id : null,
    timeout_seconds: form.timeout_seconds
  }
}

async function save() {
  if (!form.name.trim() || !form.instruction.trim()) return ElMessage.error('任务名称与指令不能为空')
  if (form.conv_mode === 'fixed' && !form.conversation_id) return ElMessage.error('请选择固定会话')
  if (form.schedule_mode === 'calendar' && !form.calendar_rule.times?.length) return ElMessage.error('请至少填写一个时刻')
  saving.value = true
  try {
    await api.post('/agent/scheduled-jobs', payload())
    dialog.value = false
    ElMessage.success('已保存')
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function toggle(row, enabled) {
  try {
    const data = await api.post(`/agent/scheduled-jobs/${row.id}/toggle`, { enabled })
    Object.assign(row, data)
  } catch {
    row.enabled = !enabled
  }
}

async function runNow(row) {
  try {
    await api.post(`/agent/scheduled-jobs/${row.id}/run-now`)
    ElMessage.success('已提交执行，稍后点「结果」查看')
  } catch {
    /* ignore */
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除定时任务「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/scheduled-jobs/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* ignore */
  }
}

function openConversation(row) {
  router.push({ path: '/chat', query: { conversation: row.last_conversation_id } })
}

onMounted(async () => {
  await load()
  timer = setInterval(() => { now.value = Date.now() }, 15000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0 18px; }
.inline { display: flex; gap: 10px; align-items: center; }
.due { color: var(--el-color-warning); font-weight: 600; }
</style>
