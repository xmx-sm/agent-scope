<template>
  <div class="page">
    <h2 class="page-title">系统设置</h2>
    <p class="page-desc">站点、账号、安全、界面与邮箱（仅超级管理员）</p>

    <div v-loading="loading">
      <div class="config-toolbar">
        <span class="muted">共 {{ configs.length }} 项，按分组折叠展示</span>
        <div class="grow"></div>
        <el-button size="small" @click="expandAll">全部展开</el-button>
        <el-button size="small" @click="collapseAll">全部收起</el-button>
      </div>
      <el-collapse v-model="openGroups" class="config-collapse">
        <el-collapse-item v-for="group in groups" :key="group.name" :name="group.name">
          <template #title>
            <span class="collapse-title">{{ group.name }}</span>
            <span class="muted collapse-count">{{ group.items.length }} 项</span>
          </template>
          <div v-for="item in group.items" :key="item.key" class="config-row">
            <div class="config-info">
              <div class="config-label">{{ item.label || item.key }}</div>
              <div class="muted">{{ item.description }}</div>
              <code class="config-key">{{ item.key }} = {{ item.default }}</code>
            </div>
            <div class="config-control">
              <el-switch v-if="item.value_type === 'bool'" v-model="item.value" />
              <el-input-number
                v-else-if="item.value_type === 'int' || item.value_type === 'float'"
                v-model="item.value"
                :min="0"
                :step="item.value_type === 'float' ? 0.1 : 1"
                :precision="item.value_type === 'float' ? 2 : 0"
                controls-position="right"
                style="width: 150px"
              />
              <el-select
                v-else-if="item.key === 'default_role'"
                v-model="item.value"
                style="width: 150px"
              >
                <el-option label="普通用户" value="user" />
                <el-option label="管理员" value="admin" />
              </el-select>
              <el-input
                v-else-if="item.secret"
                v-model="item.value"
                type="password"
                show-password
                style="width: 220px"
              />
              <el-input v-else v-model="item.value" style="width: 220px" />
              <el-button type="primary" :loading="savingKey === item.key" @click="save(item)">
                保存
              </el-button>
              <el-button
                :loading="resettingKey === item.key"
                :disabled="item.value === item.default"
                @click="reset(item)"
              >
                恢复默认
              </el-button>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'

const configs = ref([])
const loading = ref(false)
const savingKey = ref('')
const resettingKey = ref('')
const openGroups = ref([])

const groups = computed(() => {
  const map = new Map()
  for (const item of configs.value) {
    const name = item.group || '其他'
    if (!map.has(name)) map.set(name, { name, items: [] })
    map.get(name).items.push(item)
  }
  return [...map.values()]
})

async function load() {
  loading.value = true
  try {
    configs.value = await api.get('/admin/configs', { params: { domain: 'system' } })
    if (!openGroups.value.length) openGroups.value = ['站点', '账号']
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function expandAll() {
  openGroups.value = groups.value.map((group) => group.name)
}

function collapseAll() {
  openGroups.value = []
}

async function save(item) {
  savingKey.value = item.key
  try {
    await api.put(`/admin/configs/${item.key}`, { value: item.value })
    ElMessage.success(`${item.label || item.key} 已保存`)
  } catch {
    /* ignore */
  } finally {
    savingKey.value = ''
  }
}

async function reset(item) {
  resettingKey.value = item.key
  try {
    await api.post(`/admin/configs/${item.key}/reset`)
    ElMessage.success(`${item.label || item.key} 已恢复默认值`)
    item.value = item.default
  } catch {
    /* ignore */
  } finally {
    resettingKey.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.config-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.config-collapse {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

.config-collapse :deep(.el-collapse-item__header) {
  padding: 0 16px;
  background: #fafbfc;
}

.config-collapse :deep(.el-collapse-item__content) {
  padding: 0 16px 12px;
}

.collapse-title {
  font-weight: 700;
  font-size: 14px;
  margin-right: 8px;
}

.collapse-count {
  font-size: 12px;
}

.config-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 0;
  border-bottom: 1px dashed var(--app-border);
}

.config-row:last-child {
  border-bottom: none;
}

.config-label {
  font-weight: 600;
  font-size: 14px;
}

.config-key {
  display: inline-block;
  margin-top: 6px;
  font-size: 11.5px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 5px;
  padding: 1px 6px;
}

.config-control {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

@media (max-width: 767px) {
  .config-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .config-control {
    width: 100%;
  }
  .config-control :deep(.el-input-number),
  .config-control :deep(.el-input),
  .config-control :deep(.el-select) {
    flex: 1;
    width: auto !important;
  }
}
</style>
