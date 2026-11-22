<template>
  <div class="page">
    <h2 class="page-title">工具配置</h2>
    <p class="page-desc">邮箱与数据库连接；默认使用系统配置，也可以为自己的账号单独配置</p>

    <el-tabs v-model="activeTab" @tab-change="load">
      <el-tab-pane label="邮箱" name="email">
        <div class="panel" v-loading="loading">
          <el-radio-group v-model="useDefault" class="mode-switch">
            <el-radio-button :value="true">使用系统默认</el-radio-button>
            <el-radio-button :value="false">自定义配置</el-radio-button>
          </el-radio-group>

          <div v-if="useDefault" class="system-info">
            <div class="info-grid">
              <div><span class="muted">SMTP</span><b>{{ view.system.smtp_host || '未配置' }}</b></div>
              <div><span class="muted">账号</span><b>{{ view.system.host_user || '未配置' }}</b></div>
              <div><span class="muted">密码</span><b>{{ view.system.password || '未配置' }}</b></div>
              <div><span class="muted">IMAP</span><b>{{ view.system.imap_host || '未配置' }}</b></div>
            </div>
          </div>

          <el-form v-else label-position="top">
            <div class="form-grid">
              <el-form-item label="SMTP 服务器"><el-input v-model="form.smtp_host" placeholder="smtp.example.com" /></el-form-item>
              <el-form-item label="SMTP 端口"><el-input-number v-model="form.smtp_port" :min="1" :max="65535" /></el-form-item>
              <el-form-item label="邮箱账号"><el-input v-model="form.host_user" placeholder="name@example.com" /></el-form-item>
              <el-form-item label="授权码 / 密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
              <el-form-item label="IMAP 服务器"><el-input v-model="form.imap_host" placeholder="imap.example.com" /></el-form-item>
              <el-form-item label="IMAP 端口"><el-input-number v-model="form.imap_port" :min="1" :max="65535" /></el-form-item>
              <el-form-item label="发件地址"><el-input v-model="form.from_address" placeholder="留空使用邮箱账号" /></el-form-item>
              <el-form-item label="发件人名称"><el-input v-model="form.from_name" /></el-form-item>
              <el-form-item label="启用 TLS"><el-switch v-model="form.use_tls" /></el-form-item>
            </div>
          </el-form>

          <div class="save-bar">
            <el-button :loading="testing" @click="test">测试连接</el-button>
            <el-button @click="reset" :loading="resetting">恢复系统默认</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="数据库" name="db">
        <div class="panel" v-loading="loading">
          <el-radio-group v-model="useDefault" class="mode-switch">
            <el-radio-button :value="true">使用系统默认</el-radio-button>
            <el-radio-button :value="false">自定义配置</el-radio-button>
          </el-radio-group>

          <div v-if="useDefault" class="system-info">
            <div class="info-grid">
              <div><span class="muted">类型</span><b>{{ view.system.db_type || '未配置' }}</b></div>
              <div><span class="muted">主机</span><b>{{ view.system.host || '未配置' }}</b></div>
              <div><span class="muted">数据库</span><b>{{ view.system.database || '未配置' }}</b></div>
              <div><span class="muted">允许写入</span><b>{{ view.system.allow_write ? '是' : '否' }}</b></div>
            </div>
          </div>

          <el-form v-else label-position="top">
            <div class="form-grid">
              <el-form-item label="数据库类型">
                <el-select v-model="form.db_type" style="width: 100%">
                  <el-option label="PostgreSQL" value="postgresql" />
                  <el-option label="MySQL" value="mysql" />
                  <el-option label="MongoDB" value="mongodb" />
                  <el-option label="SQLite" value="sqlite" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="form.db_type !== 'sqlite'" label="主机"><el-input v-model="form.host" /></el-form-item>
              <el-form-item v-if="form.db_type !== 'sqlite'" label="端口"><el-input-number v-model="form.port" :min="0" :max="65535" /></el-form-item>
              <el-form-item v-if="form.db_type !== 'sqlite'" label="账号"><el-input v-model="form.user" /></el-form-item>
              <el-form-item v-if="form.db_type !== 'sqlite'" label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
              <el-form-item v-if="form.db_type !== 'sqlite'" label="数据库名"><el-input v-model="form.database" /></el-form-item>
              <el-form-item v-if="form.db_type === 'sqlite'" label="SQLite 文件"><el-input v-model="form.path" placeholder="/path/to/db.sqlite" /></el-form-item>
              <el-form-item v-if="form.db_type === 'sqlite'" label="SQLite 文件夹"><el-input v-model="form.dir" placeholder="/path/to/sqlite_dir" /></el-form-item>
            </div>
          </el-form>

          <div class="save-bar">
            <el-button :loading="testing" @click="test">测试连接</el-button>
            <el-button @click="reset" :loading="resetting">恢复系统默认</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const activeTab = ref('email')
const loading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const testing = ref(false)
const useDefault = ref(true)
const view = ref({ system: {}, user: {}, effective: {} })
const form = reactive({
  smtp_host: '',
  smtp_port: 465,
  host_user: '',
  password: '',
  imap_host: '',
  imap_port: 993,
  from_address: '',
  from_name: 'Agent Scope',
  use_tls: true,
  db_type: 'postgresql',
  host: '',
  port: 0,
  user: '',
  database: '',
  path: '',
  dir: '',
  allow_write: false
})

async function load() {
  loading.value = true
  try {
    const data = await api.get(`/agent/tool-config/${activeTab.value}`)
    view.value = data
    useDefault.value = data.use_default
    const source = data.use_default ? data.system : { ...data.system, ...data.user }
    Object.assign(form, source)
    if (activeTab.value === 'db') form.password = data.user.password || data.system.password || ''
    else form.password = data.user.password || data.system.password || ''
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const data = await api.put(`/agent/tool-config/${activeTab.value}`, {
      use_default: useDefault.value,
      config: { ...form }
    })
    view.value = data
    useDefault.value = data.use_default
    ElMessage.success('工具配置已保存')
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function reset() {
  resetting.value = true
  try {
    view.value = await api.delete(`/agent/tool-config/${activeTab.value}`)
    useDefault.value = true
    ElMessage.success('已恢复系统默认')
    await load()
  } catch {
    /* ignore */
  } finally {
    resetting.value = false
  }
}

async function test() {
  testing.value = true
  try {
    const data = await api.post(`/agent/tool-config/${activeTab.value}/test`)
    ElMessage.success(
      activeTab.value === 'email' ? '邮箱连接成功' : `数据库连接成功（${data.databases?.length || 0} 个库）`
    )
  } catch {
    /* ignore */
  } finally {
    testing.value = false
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
  font-size: 13px;
}

.info-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 0 20px;
}

.save-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
