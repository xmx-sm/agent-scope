<template>
  <div class="page">
    <h2 class="page-title">菜单个性化</h2>
    <p class="page-desc">在管理员默认菜单的基础上，调整自己的菜单顺序与显示项</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <span class="muted">“菜单个性化”入口不可隐藏，避免无法恢复</span>
        <div class="grow"></div>
        <el-button @click="reset">恢复默认</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>

      <div v-for="(root, ri) in roots" :key="root.key" class="pref-group">
        <div class="pref-row pref-parent">
          <div class="pref-title">
            <el-icon><component :is="root.icon || 'Menu'" /></el-icon>
            <span>{{ root.title }}</span>
            <el-tag v-if="root.path" size="small" effect="plain">{{ root.path }}</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">分组</el-tag>
          </div>
          <div class="pref-actions">
            <el-switch
              v-model="root.visible"
              :disabled="root.key === LOCKED_KEY"
              size="small"
              active-text="显示"
            />
            <el-button size="small" :disabled="ri === 0" @click="move(roots, ri, -1)">上移</el-button>
            <el-button size="small" :disabled="ri === roots.length - 1" @click="move(roots, ri, 1)">下移</el-button>
          </div>
        </div>

        <div v-if="root.children.length" class="pref-children">
          <div v-for="(child, ci) in root.children" :key="child.key" class="pref-row">
            <div class="pref-title pref-child-title">
              <el-icon><component :is="child.icon || 'Menu'" /></el-icon>
              <span>{{ child.title }}</span>
              <el-tag size="small" effect="plain">{{ child.path }}</el-tag>
            </div>
            <div class="pref-actions">
              <el-switch
                v-model="child.visible"
                :disabled="child.key === LOCKED_KEY || !root.visible"
                size="small"
              />
              <el-button size="small" :disabled="ci === 0" @click="move(root.children, ci, -1)">上移</el-button>
              <el-button size="small" :disabled="ci === root.children.length - 1" @click="move(root.children, ci, 1)">
                下移
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <el-empty v-if="!roots.length && !loading" description="暂无可配置菜单" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const LOCKED_KEY = 'menu.personalize'
const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const roots = ref([])

function markVisible(nodes) {
  const hidden = new Set(nodes.hidden || [])
  for (const root of nodes) {
    root.visible = !hidden.has(root.key)
    for (const child of root.children || []) child.visible = !hidden.has(child.key)
  }
  return nodes
}

async function load() {
  loading.value = true
  try {
    const [catalog, prefs] = await Promise.all([
      api.get('/menus/catalog'),
      api.get('/menus/prefs')
    ])
    const hidden = new Set(prefs.hidden || [])
    const order = prefs.order || {}

    const rank = (list, key) => {
      const index = (list || []).indexOf(key)
      return index === -1 ? 10 ** 6 : index
    }
    catalog.sort((a, b) => rank(order.root, a.key) - rank(order.root, b.key))
    for (const root of catalog) {
      root.visible = !hidden.has(root.key)
      root.children = (root.children || []).sort(
        (a, b) => rank(order[root.key], a.key) - rank(order[root.key], b.key)
      )
      for (const child of root.children) child.visible = !hidden.has(child.key)
    }
    roots.value = catalog
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function move(list, index, direction) {
  const target = index + direction
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target], list[index]]
}

function collectHidden() {
  const hidden = []
  for (const root of roots.value) {
    if (!root.visible) hidden.push(root.key)
    for (const child of root.children || []) {
      if (!child.visible) hidden.push(child.key)
    }
  }
  return hidden
}

function collectOrder() {
  const order = { root: roots.value.map((item) => item.key) }
  for (const root of roots.value) {
    if (root.children?.length) order[root.key] = root.children.map((item) => item.key)
  }
  return order
}

async function save() {
  saving.value = true
  try {
    await api.put('/menus/prefs', { order: collectOrder(), hidden: collectHidden() })
    ElMessage.success('菜单个性化已保存')
    await auth.fetchMenus()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function reset() {
  try {
    await ElMessageBox.confirm('确定恢复默认菜单顺序与显示项吗？', '恢复默认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete('/menus/prefs')
    ElMessage.success('已恢复默认')
    await auth.fetchMenus()
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
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.pref-group {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  margin-bottom: 12px;
  overflow: hidden;
}

.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px dashed var(--app-border);
  flex-wrap: wrap;
}

.pref-row:last-child {
  border-bottom: none;
}

.pref-parent {
  background: #f8fafc;
  font-weight: 600;
}

.pref-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.pref-child-title {
  padding-left: 18px;
  font-weight: 400;
}

.pref-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pref-children .pref-row {
  padding-left: 28px;
}
</style>
