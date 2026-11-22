<template>
  <div class="page">
    <div class="stats-head">
      <div>
        <h2 class="page-title">Agent 统计</h2>
        <p class="page-desc">模型调用次数与 token 用量</p>
      </div>
      <div class="stats-actions">
        <el-radio-group v-if="auth.isSuperAdmin" v-model="scope" size="small" @change="load">
          <el-radio-button value="user">我的</el-radio-button>
          <el-radio-button value="global">全平台</el-radio-button>
        </el-radio-group>
        <el-select v-model="days" size="small" style="width: 110px" @change="load">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
        </el-select>
      </div>
    </div>

    <div v-loading="loading">
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">会话数</div>
          <div class="stat-value">{{ data.totals?.conversations ?? 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">消息数</div>
          <div class="stat-value">{{ data.totals?.messages ?? 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">模型调用</div>
          <div class="stat-value">{{ data.totals?.calls ?? 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总 tokens</div>
          <div class="stat-value">{{ formatNumber(data.totals?.total_tokens) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">输入 / 输出</div>
          <div class="stat-value small">
            {{ formatNumber(data.totals?.input_tokens) }} / {{ formatNumber(data.totals?.output_tokens) }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">缓存输入</div>
          <div class="stat-value small">{{ formatNumber(data.totals?.cache_input_tokens) }}</div>
        </div>
      </div>

      <div class="panel">
        <h3 class="card-title">每日用量</h3>
        <div v-if="data.by_day?.length" class="day-chart">
          <div v-for="day in data.by_day" :key="day.date" class="day-item">
            <div class="bar-wrap">
              <div
                class="bar"
                :style="{ height: `${barHeight(day)}%` }"
                :title="`${day.date}：${formatNumber(day.input_tokens + day.output_tokens)} tokens`"
              ></div>
            </div>
            <div class="day-label">{{ day.date.slice(5) }}</div>
            <div class="day-value">{{ formatNumber(day.input_tokens + day.output_tokens) }}</div>
          </div>
        </div>
        <el-empty v-else description="暂无数据" :image-size="60" />
      </div>

      <div class="panel">
        <h3 class="card-title">按模型</h3>
        <el-table :data="data.by_model || []" size="small" stripe>
          <el-table-column prop="model" label="模型" min-width="180" />
          <el-table-column prop="calls" label="调用次数" width="100" />
          <el-table-column label="输入" width="120">
            <template #default="{ row }">{{ formatNumber(row.input_tokens) }}</template>
          </el-table-column>
          <el-table-column label="输出" width="120">
            <template #default="{ row }">{{ formatNumber(row.output_tokens) }}</template>
          </el-table-column>
          <el-table-column label="缓存" width="120">
            <template #default="{ row }">{{ formatNumber(row.cache_input_tokens) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.input_tokens + row.output_tokens) }}
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="scope === 'global'" class="panel">
        <h3 class="card-title">按用户</h3>
        <el-table :data="data.by_user || []" size="small" stripe>
          <el-table-column prop="user_name" label="用户" min-width="140" />
          <el-table-column prop="calls" label="调用次数" width="100" />
          <el-table-column label="输入" width="120">
            <template #default="{ row }">{{ formatNumber(row.input_tokens) }}</template>
          </el-table-column>
          <el-table-column label="输出" width="120">
            <template #default="{ row }">{{ formatNumber(row.output_tokens) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.input_tokens + row.output_tokens) }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const auth = useAuthStore()
const loading = ref(false)
const days = ref(7)
const scope = ref('user')
const data = ref({ totals: {}, by_model: [], by_day: [], by_user: [] })

const maxDay = computed(() =>
  Math.max(1, ...(data.value.by_day || []).map((d) => d.input_tokens + d.output_tokens))
)

function barHeight(day) {
  const total = day.input_tokens + day.output_tokens
  return Math.max(2, Math.round((total / maxDay.value) * 100))
}

function formatNumber(value) {
  const num = Number(value || 0)
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`
  return String(num)
}

async function load() {
  loading.value = true
  try {
    const url = scope.value === 'global' ? '/admin/agent/stats' : '/agent/stats'
    data.value = await api.get(url, { params: { days: days.value } })
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.stats-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.stats-actions {
  display: flex;
  gap: 10px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #fff;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 16px;
}

.stat-label {
  color: var(--app-muted);
  font-size: 12px;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  margin-top: 4px;
}

.stat-value.small {
  font-size: 18px;
}

.panel {
  margin-bottom: 16px;
}

.card-title {
  margin: 0 0 14px;
  font-size: 15px;
}

.day-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 170px;
  overflow-x: auto;
  padding-top: 8px;
}

.day-item {
  flex: 1;
  min-width: 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.bar-wrap {
  height: 120px;
  width: 100%;
  display: flex;
  align-items: flex-end;
}

.bar {
  width: 100%;
  background: linear-gradient(180deg, #60a5fa, #2563eb);
  border-radius: 4px 4px 0 0;
  min-height: 2px;
}

.day-label {
  font-size: 11px;
  color: var(--app-muted);
}

.day-value {
  font-size: 10px;
  color: var(--app-muted);
}

@media (max-width: 767px) {
  .stat-grid {
    grid-template-columns: 1fr 1fr;
  }
  .stat-value {
    font-size: 20px;
  }
}
</style>
