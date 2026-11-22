<template>
  <div class="page">
    <h2 class="page-title">团队权限</h2>
    <p class="page-desc">你可以收缩自己管理链上全部下属的权限；收缩不可由下属自行恢复</p>

    <div class="panel" v-loading="loading">
      <div v-for="member in members" :key="member.id" class="member-card">
        <div class="member-head">
          <div class="member-avatar">{{ (member.nickname || member.username).slice(0, 1) }}</div>
          <div class="grow">
            <div class="member-name">
              {{ member.nickname }}
              <span class="muted">@{{ member.username }}</span>
            </div>
            <div class="member-tags">
              <el-tag size="small" effect="plain">{{ roleLabel(member.role) }}</el-tag>
              <el-tag v-if="!member.is_active" size="small" type="info">已禁用</el-tag>
              <el-tag v-for="temp in member.temp_grants" :key="temp.permission" size="small" type="warning" effect="plain">
                临时：{{ nameOf(temp.permission) }}
              </el-tag>
            </div>
          </div>
          <el-button
            type="danger"
            plain
            size="small"
            :disabled="!member.shrinkable.length"
            @click="openShrink(member)"
          >
            收缩权限
          </el-button>
        </div>
        <div class="chip-list">
          <el-tag v-for="key in member.permissions" :key="key" size="small" type="success" effect="light">
            {{ nameOf(key) }}
          </el-tag>
          <span v-if="!member.permissions.length" class="muted">暂无有效权限</span>
        </div>
      </div>
      <el-empty v-if="!members.length && !loading" description="暂无下属成员" />
    </div>

    <el-dialog v-model="dialogVisible" title="收缩下属权限" :width="isMobile ? '92%' : '480px'">
      <p class="muted">
        正在调整：<b>{{ target?.nickname }}</b>。勾选要移除的权限，保存后立即生效。
      </p>
      <el-checkbox-group v-model="selected" class="shrink-list">
        <el-checkbox v-for="key in target?.shrinkable || []" :key="key" :value="key" :label="key">
          {{ nameOf(key) }}
        </el-checkbox>
      </el-checkbox-group>
      <el-empty v-if="!target?.shrinkable?.length" description="没有可收缩的权限" :image-size="60" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="danger" :disabled="!selected.length" :loading="saving" @click="shrink">
          确定收缩
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const saving = ref(false)
const members = ref([])
const catalog = ref([])
const dialogVisible = ref(false)
const target = ref(null)
const selected = ref([])

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
function roleLabel(role) {
  return roleLabels[role] || role
}
function nameOf(key) {
  return catalog.value.find((item) => item.key === key)?.name || key
}

async function load() {
  loading.value = true
  try {
    const data = await api.get('/permissions/team')
    members.value = data.members
    catalog.value = data.catalog
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openShrink(member) {
  target.value = member
  selected.value = []
  dialogVisible.value = true
}

async function shrink() {
  if (!selected.value.length) return
  saving.value = true
  try {
    await api.post(`/permissions/team/${target.value.id}/shrink`, {
      permissions: selected.value
    })
    ElMessage.success('下属权限已收缩')
    dialogVisible.value = false
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
.member-card {
  border-bottom: 1px dashed var(--app-border);
  padding: 14px 0;
}

.member-card:first-child {
  padding-top: 0;
}

.member-card:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.member-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.member-avatar {
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

.member-name {
  font-weight: 600;
  font-size: 14px;
}

.member-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 5px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.shrink-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}

@media (max-width: 767px) {
  .member-head {
    flex-wrap: wrap;
  }
  .member-head .el-button {
    margin-left: 48px;
  }
}
</style>
