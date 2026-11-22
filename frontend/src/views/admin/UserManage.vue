<template>
  <div class="page">
    <h2 class="page-title">用户管理</h2>
    <p class="page-desc">管理账号、角色和汇报关系（仅超级管理员）</p>

    <div class="panel">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索用户名 / 昵称 / 邮箱 / 手机号"
          clearable
          class="search"
          @keyup.enter="load(1)"
          @clear="load(1)"
        />
        <el-select v-model="roleFilter" placeholder="全部角色" clearable class="role-select" @change="load(1)">
          <el-option v-for="role in roles" :key="role.value" :label="role.label" :value="role.value" />
        </el-select>
        <el-button type="primary" @click="load(1)">查询</el-button>
        <div class="grow"></div>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增用户</el-button>
      </div>

      <!-- 桌面表格 -->
      <el-table v-if="!isMobile" v-loading="loading" :data="users" stripe>
        <el-table-column prop="username" label="用户名" min-width="110" />
        <el-table-column prop="nickname" label="昵称" min-width="100" />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)" effect="plain">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="leader_name" label="直属上级" min-width="100">
          <template #default="{ row }">{{ row.leader_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="160">
          <template #default="{ row }">{{ row.email || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" effect="light">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.role !== 'super_admin'" link type="success" @click="openPermission(row)">权限</el-button>
            <el-button link type="warning" @click="openReset(row)">重置密码</el-button>
            <el-button link type="danger" @click="removeUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-else v-loading="loading" class="cards">
        <div v-for="row in users" :key="row.id" class="user-card">
          <div class="uc-head">
            <div class="uc-avatar">{{ (row.nickname || row.username).slice(0, 1) }}</div>
            <div class="grow">
              <div class="uc-name">{{ row.nickname }} <span class="muted">@{{ row.username }}</span></div>
              <div class="uc-tags">
                <el-tag size="small" :type="roleTag(row.role)" effect="plain">{{ roleLabel(row.role) }}</el-tag>
                <el-tag size="small" :type="row.is_active ? 'success' : 'info'" effect="light">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </div>
            </div>
          </div>
          <div class="uc-meta">
            <div>上级：{{ row.leader_name || '—' }}</div>
            <div>邮箱：{{ row.email || '—' }}</div>
          </div>
          <div class="uc-actions">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.role !== 'super_admin'" size="small" type="success" plain @click="openPermission(row)">权限</el-button>
            <el-button size="small" type="warning" plain @click="openReset(row)">重置密码</el-button>
            <el-button size="small" type="danger" plain @click="removeUser(row)">删除</el-button>
          </div>
        </div>
        <el-empty v-if="!users.length && !loading" description="暂无用户" />
      </div>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          :layout="isMobile ? 'prev, pager, next' : 'total, prev, pager, next'"
          :pager-count="isMobile ? 5 : 7"
          background
          @current-change="load"
        />
      </div>
    </div>

    <!-- 新增/编辑 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新增用户'" :width="isMobile ? '92%' : '520px'">
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="editing" placeholder="登录账号" />
        </el-form-item>
        <el-form-item v-if="!editing" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="form.nickname" placeholder="默认与用户名一致" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="role in roleOptions" :key="role.value" :label="role.label" :value="role.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="直属上级">
          <el-select v-model="form.leader_id" clearable placeholder="无" style="width: 100%">
            <el-option
              v-for="u in leaderOptions"
              :key="u.id"
              :label="`${u.nickname}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="选填" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 权限配置 -->
    <el-dialog v-model="permissionVisible" title="用户权限配置" :width="isMobile ? '94%' : '640px'">
      <div v-if="permissionDetail" class="perm-dialog">
        <div class="perm-user">
          <b>{{ permissionTarget?.nickname }}</b>
          <span class="muted">@{{ permissionTarget?.username }} · {{ roleLabel(permissionTarget?.role) }}</span>
        </div>
        <div class="perm-section">
          <div class="perm-section-title">当前有效权限</div>
          <div class="chip-list">
            <el-tag v-for="key in permissionDetail.effective" :key="key" size="small" type="success" effect="light">
              {{ permName(key) }}
            </el-tag>
          </div>
        </div>

        <div class="perm-section">
          <div class="perm-section-title">单独授权（叠加在角色权限之上）</div>
          <el-checkbox-group v-model="grantedSel" class="perm-checks">
            <el-checkbox v-for="item in assignablePerms" :key="item.key" :value="item.key" :label="item.key">
              {{ item.name }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="perm-section">
          <div class="perm-section-title">收缩权限（只增不减）</div>
          <el-checkbox-group v-model="shrunkSel" class="perm-checks">
            <el-checkbox v-for="item in assignablePerms" :key="item.key" :value="item.key" :label="item.key">
              {{ item.name }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="perm-section">
          <div class="perm-section-title">临时越级授权</div>
          <div v-for="(item, index) in tempList" :key="index" class="temp-row">
            <el-select v-model="item.permission" placeholder="选择权限" style="flex: 1">
              <el-option v-for="perm in permissionCatalog" :key="perm.key" :label="perm.name" :value="perm.key" />
            </el-select>
            <el-date-picker
              v-model="item.expires_at"
              type="datetime"
              placeholder="过期时间"
              style="flex: 1"
            />
            <el-button text type="danger" @click="tempList.splice(index, 1)">移除</el-button>
          </div>
          <el-button size="small" plain @click="addTemp">+ 添加临时授权</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="permissionVisible = false">取消</el-button>
        <el-button type="primary" :loading="permSaving" @click="savePermissions">保存权限</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" :width="isMobile ? '88%' : '420px'">
      <p class="muted">为用户 <b>{{ resetTarget?.nickname }}</b> 设置新密码</p>
      <el-input v-model="resetPassword" type="password" show-password placeholder="至少 6 位" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="doReset">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const keyword = ref('')
const roleFilter = ref('')

const roles = [
  { value: 'super_admin', label: '超级管理员' },
  { value: 'admin', label: '管理员' },
  { value: 'user', label: '普通用户' }
]
const roleOptions = computed(() =>
  auth.isSuperAdmin ? roles : roles.filter((r) => r.value !== 'super_admin')
)

const dialogVisible = ref(false)
const editing = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive(emptyForm())

const permissionVisible = ref(false)
const permissionTarget = ref(null)
const permissionDetail = ref(null)
const grantedSel = ref([])
const shrunkSel = ref([])
const tempList = ref([])
const permSaving = ref(false)

const resetVisible = ref(false)
const resetTarget = ref(null)
const resetPassword = ref('')
const resetting = ref(false)

const permissionCatalog = computed(() => permissionDetail.value?.catalog || [])
const assignablePerms = computed(() =>
  permissionCatalog.value.filter((item) => !item.super_only)
)
const leaderList = ref([])
const leaderOptions = computed(() =>
  leaderList.value.filter((u) => !editing.value || u.id !== form.id)
)

const formRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入初始密码', trigger: 'blur' }, { min: 6, message: '至少 6 位', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

function emptyForm() {
  return {
    id: '',
    username: '',
    password: '',
    nickname: '',
    role: 'user',
    leader_id: '',
    email: '',
    phone: '',
    is_active: true
  }
}

function roleLabel(role) {
  return roles.find((r) => r.value === role)?.label || role
}
function roleTag(role) {
  return role === 'super_admin' ? 'danger' : role === 'admin' ? 'warning' : 'info'
}

async function load(target = page.value) {
  loading.value = true
  page.value = target
  try {
    const data = await api.get('/admin/users', {
      params: { page: target, page_size: pageSize, keyword: keyword.value, role: roleFilter.value }
    })
    users.value = data.items
    total.value = data.total
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function loadLeaders() {
  try {
    const data = await api.get('/admin/users', { params: { page: 1, page_size: 100 } })
    leaderList.value = data.items
  } catch {
    /* ignore */
  }
}

function openCreate() {
  loadLeaders()
  editing.value = false
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

function openEdit(row) {
  loadLeaders()
  editing.value = true
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    nickname: row.nickname,
    role: row.role,
    leader_id: row.leader_id || '',
    email: row.email || '',
    phone: row.phone || '',
    is_active: row.is_active
  })
  dialogVisible.value = true
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      nickname: form.nickname.trim() || null,
      role: form.role,
      leader_id: form.leader_id || null,
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      is_active: form.is_active
    }
    if (editing.value) {
      await api.put(`/admin/users/${form.id}`, payload)
      ElMessage.success('用户已更新')
    } else {
      await api.post('/admin/users', {
        ...payload,
        username: form.username.trim(),
        password: form.password
      })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await load(editing.value ? page.value : 1)
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

function permName(key) {
  return permissionDetail.value?.catalog?.find((item) => item.key === key)?.name || key
}

async function openPermission(row) {
  permissionTarget.value = row
  permissionVisible.value = true
  permissionDetail.value = null
  try {
    const data = await api.get(`/admin/users/${row.id}/permissions`)
    permissionDetail.value = data
    grantedSel.value = [...(data.granted || [])]
    shrunkSel.value = [...(data.shrunk || [])]
    tempList.value = (data.temp_grants || []).map((item) => ({
      permission: item.permission,
      expires_at: new Date(item.expires_at)
    }))
  } catch {
    permissionVisible.value = false
  }
}

function addTemp() {
  const now = new Date(Date.now() + 24 * 3600 * 1000)
  tempList.value.push({ permission: '', expires_at: now })
}

async function savePermissions() {
  const temps = tempList.value
    .filter((item) => item.permission && item.expires_at)
    .map((item) => ({
      permission: item.permission,
      expires_at: new Date(item.expires_at).toISOString()
    }))
  permSaving.value = true
  try {
    await api.put(`/admin/users/${permissionTarget.value.id}/permissions`, {
      granted: grantedSel.value,
      shrunk: shrunkSel.value,
      temp_grants: temps
    })
    ElMessage.success('权限已保存')
    permissionVisible.value = false
  } catch {
    /* ignore */
  } finally {
    permSaving.value = false
  }
}

function openReset(row) {
  resetTarget.value = row
  resetPassword.value = ''
  resetVisible.value = true
}

async function doReset() {
  if (resetPassword.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  resetting.value = true
  try {
    await api.post(`/admin/users/${resetTarget.value.id}/reset-password`, {
      new_password: resetPassword.value
    })
    ElMessage.success('密码已重置')
    resetVisible.value = false
  } catch {
    /* ignore */
  } finally {
    resetting.value = false
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除用户「${row.nickname}（${row.username}）」吗？该操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return
  }
  try {
    await api.delete(`/admin/users/${row.id}`)
    ElMessage.success('用户已删除')
    if (users.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  window.addEventListener('resize', () => (isMobile.value = window.innerWidth < 768))
  load(1)
})
</script>

<style scoped>
.search {
  width: 280px;
}

.role-select {
  width: 150px;
}

.cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-card {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 13px;
  background: #fff;
}

.uc-head {
  display: flex;
  gap: 10px;
  align-items: center;
}

.uc-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex: none;
}

.uc-name {
  font-weight: 600;
  font-size: 14px;
}

.uc-tags {
  display: flex;
  gap: 6px;
  margin-top: 5px;
}

.uc-meta {
  margin: 10px 0;
  font-size: 12.5px;
  color: var(--app-muted);
  line-height: 1.8;
}

.uc-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.perm-user {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 14px;
}

.perm-section {
  margin-bottom: 16px;
}

.perm-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.perm-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.temp-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 767px) {
  .search {
    width: 100%;
    flex: 1 1 100%;
  }
  .role-select {
    flex: 1;
    width: auto;
  }
  .perm-user {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 14px;
}

.perm-section {
  margin-bottom: 16px;
}

.perm-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.perm-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.temp-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.pager {
    justify-content: center;
  }
}
</style>
