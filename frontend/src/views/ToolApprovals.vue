<template>
  <div class="page">
    <h2 class="page-title">工具审批</h2>
    <p class="page-desc">下级申请启用需审批的工具时，在这里通过或拒绝；通过后会写入该用户的工具授权。</p>
    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <el-tag type="warning" effect="plain">待处理 {{ items.length }}</el-tag>
        <div class="grow"></div>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-table :data="items" size="small" stripe>
        <el-table-column prop="user_name" label="申请人" width="120" />
        <el-table-column prop="tool_group" label="工具组" width="110" />
        <el-table-column prop="tool_name" label="工具" min-width="150" />
        <el-table-column prop="reason" label="申请原因" min-width="220" show-overflow-tooltip />
        <el-table-column prop="created_at" label="申请时间" width="180" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="decide(row, true)">通过</el-button>
            <el-button link type="danger" @click="decide(row, false)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!items.length && !loading" description="没有待处理审批" :image-size="70" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '../utils/api'

const items = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    items.value = await api.get('/tools/approvals')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function decide(row, approve) {
  try {
    await api.post(`/tools/approvals/${row.id}/decide`, { approve })
    ElMessage.success(approve ? '已通过' : '已拒绝')
    await load()
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
</style>
