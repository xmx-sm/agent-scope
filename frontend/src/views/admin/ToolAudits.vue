<template>
  <div class="page">
    <h2 class="page-title">工具权限审计</h2>
    <p class="page-desc">记录授权、收窄、重置、审批等工具权限变更；仅超级管理员可见。</p>
    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <el-input v-model="userId" placeholder="按用户 ID 过滤" clearable style="width: 250px" />
        <el-input v-model="actorId" placeholder="按操作人 ID 过滤" clearable style="width: 250px" />
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>
      <el-table :data="items" size="small" stripe>
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="action" label="动作" width="140" />
        <el-table-column prop="tool_group" label="工具组" width="110" />
        <el-table-column prop="tool_name" label="工具" min-width="150" />
        <el-table-column prop="user_id" label="目标用户" min-width="230" show-overflow-tooltip />
        <el-table-column prop="actor_id" label="操作人" min-width="230" show-overflow-tooltip />
        <el-table-column label="变化" min-width="220">
          <template #default="{ row }">
            <span class="muted">{{ row.prev_state || '—' }}</span>
            <span> → </span>
            <span>{{ row.new_state || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          layout="prev, pager, next, total"
          :total="total"
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../../utils/api'

const items = ref([])
const loading = ref(false)
const userId = ref('')
const actorId = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

async function load() {
  loading.value = true
  try {
    const data = await api.get('/admin/tool-audits', {
      params: {
        page: page.value,
        page_size: pageSize,
        user_id: userId.value || undefined,
        actor_id: actorId.value || undefined
      }
    })
    items.value = data.items
    total.value = data.total ?? data.items.length
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function reset() {
  userId.value = ''
  actorId.value = ''
  page.value = 1
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
