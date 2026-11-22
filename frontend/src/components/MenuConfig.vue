<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div class="muted">支持两级菜单：一级可作为分组，子菜单挂在分组下；排序按数值升序。</div>
      <div class="grow"></div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增菜单</el-button>
    </div>

    <el-table :data="orderedMenus" stripe size="small">
      <el-table-column label="菜单" min-width="170">
        <template #default="{ row }">
          <span :class="{ 'child-title': row.parent_key }">
            {{ row.parent_key ? '↳ ' : '' }}{{ row.title }}
          </span>
          <div class="muted key-text">{{ row.key }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="path" label="路径" min-width="150">
        <template #default="{ row }">{{ row.path || '（分组）' }}</template>
      </el-table-column>
      <el-table-column label="图标" width="90">
        <template #default="{ row }">
          <el-icon :size="18"><component :is="row.icon || 'Menu'" /></el-icon>
          <span class="icon-text">{{ row.icon }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="permission" label="权限点" min-width="140">
        <template #default="{ row }">{{ row.permission || '—' }}</template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="70" />
      <el-table-column label="可见" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_visible ? 'success' : 'info'">
            {{ row.is_visible ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="move(row, -1)">上移</el-button>
          <el-button link type="primary" @click="move(row, 1)">下移</el-button>
          <el-button link type="success" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="removeMenu(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑菜单' : '新增菜单'" :width="isMobile ? '94%' : '560px'">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="菜单 Key" prop="key">
          <el-input v-model="form.key" :disabled="editing" placeholder="唯一标识，如 menu.reports" />
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="父级菜单">
          <el-select v-model="form.parent_key" clearable placeholder="无（一级菜单）" style="width: 100%">
            <el-option v-for="item in rootOptions" :key="item.key" :label="item.title" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="form.path" placeholder="分组留空；页面如 /system/status" />
        </el-form-item>
        <el-form-item label="图标">
          <div class="icon-row">
            <el-icon :size="20"><component :is="form.icon || 'Menu'" /></el-icon>
            <el-select v-model="form.icon" filterable allow-create style="flex: 1">
              <el-option v-for="name in iconOptions" :key="name" :label="name" :value="name" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="权限点">
          <el-select v-model="form.permission" clearable placeholder="不校验权限" style="width: 100%">
            <el-option
              v-for="item in permissionOptions"
              :key="item.key"
              :label="`${item.name}（${item.key}）`"
              :value="item.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序值">
          <el-input-number v-model="form.sort_order" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item label="可见性">
          <el-switch v-model="form.is_visible" active-text="显示" inactive-text="隐藏" />
          <el-switch v-model="form.super_only" active-text="仅超管" style="margin-left: 16px" />
          <el-switch v-model="form.leader_only" active-text="仅上级" style="margin-left: 16px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const saving = ref(false)
const menus = ref([])
const permissionOptions = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const formRef = ref()

const iconOptions = [
  'Menu', 'Grid', 'Key', 'Avatar', 'Setting', 'User', 'UserFilled', 'Monitor',
  'House', 'ChatDotRound', 'Document', 'DataAnalysis', 'Lock', 'Bell', 'Files',
  'Connection', 'Cpu', 'Coin', 'Star', 'Tools', 'OfficeBuilding', 'Message',
  'Calendar', 'List', 'Odometer', 'Share', 'Promotion', 'Box', 'Compass'
]

const form = reactive(emptyForm())
const rules = {
  key: [{ required: true, message: '请输入菜单 Key', trigger: 'blur' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }]
}

const rootOptions = computed(() =>
  menus.value.filter((item) => !item.parent_key && !item.path)
)

const orderedMenus = computed(() => {
  const roots = menus.value
    .filter((item) => !item.parent_key)
    .sort((a, b) => a.sort_order - b.sort_order)
  const result = []
  for (const root of roots) {
    result.push(root)
    const children = menus.value
      .filter((item) => item.parent_key === root.key)
      .sort((a, b) => a.sort_order - b.sort_order)
    result.push(...children)
  }
  return result
})

function emptyForm() {
  return {
    id: '',
    key: '',
    parent_key: '',
    title: '',
    path: '',
    icon: 'Menu',
    permission: '',
    super_only: false,
    leader_only: false,
    sort_order: 100,
    is_visible: true
  }
}

async function load() {
  loading.value = true
  try {
    const [menuData, permData] = await Promise.all([
      api.get('/admin/menus'),
      api.get('/admin/permissions')
    ])
    menus.value = menuData.menus
    permissionOptions.value = permData.all_permissions || []
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
    key: row.key,
    parent_key: row.parent_key || '',
    title: row.title,
    path: row.path || '',
    icon: row.icon || 'Menu',
    permission: row.permission || '',
    super_only: row.super_only,
    leader_only: row.leader_only,
    sort_order: row.sort_order,
    is_visible: row.is_visible
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
      parent_key: form.parent_key || null,
      title: form.title,
      path: form.path,
      icon: form.icon || 'Menu',
      permission: form.permission || null,
      super_only: form.super_only,
      leader_only: form.leader_only,
      sort_order: form.sort_order,
      is_visible: form.is_visible
    }
    if (editing.value) {
      await api.put(`/admin/menus/${form.id}`, payload)
      ElMessage.success('菜单已更新')
    } else {
      await api.post('/admin/menus', { ...payload, key: form.key.trim() })
      ElMessage.success('菜单已创建')
    }
    dialogVisible.value = false
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function move(row, direction) {
  const siblings = menus.value
    .filter((item) => (item.parent_key || null) === (row.parent_key || null))
    .sort((a, b) => a.sort_order - b.sort_order)
  const index = siblings.findIndex((item) => item.id === row.id)
  const target = index + direction
  if (target < 0 || target >= siblings.length) return
  ;[siblings[index], siblings[target]] = [siblings[target], siblings[index]]
  try {
    await Promise.all(
      siblings.map((item, i) =>
        item.sort_order === (i + 1) * 10
          ? Promise.resolve()
          : api.put(`/admin/menus/${item.id}`, { sort_order: (i + 1) * 10 })
      )
    )
    await load()
  } catch {
    /* ignore */
  }
}

async function removeMenu(row) {
  try {
    await ElMessageBox.confirm(`确定删除菜单「${row.title}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/admin/menus/${row.id}`)
    ElMessage.success('菜单已删除')
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
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.key-text {
  font-size: 11px;
  margin-top: 2px;
}

.child-title {
  padding-left: 6px;
}

.icon-text {
  font-size: 11px;
  color: var(--app-muted);
  margin-left: 6px;
}

.icon-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

@media (max-width: 767px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
