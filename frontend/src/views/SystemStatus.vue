<template>
  <div class="page">
    <div class="status-head">
      <div>
        <h2 class="page-title">运行状态</h2>
        <p class="page-desc">宿主机与依赖服务实时状态</p>
      </div>
      <div class="status-actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
        <el-button type="primary" plain :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div v-loading="loading && !data">
      <template v-if="data">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">主机</div>
            <div class="stat-main">{{ data.system.node }}</div>
            <div class="muted">{{ data.system.system }} · {{ data.system.machine }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">主 IP</div>
            <div class="stat-main">{{ data.network.primary_ip || '—' }}</div>
            <div class="muted">连接数 {{ data.network.connections }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">运行时长</div>
            <div class="stat-main">{{ uptimeText(data.app.uptime_seconds) }}</div>
            <div class="muted">Python {{ data.app.python }} · {{ data.app.env }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">进程数</div>
            <div class="stat-main">{{ data.process.total }}</div>
            <div class="muted">运行 {{ data.process.running }} · 休眠 {{ data.process.sleeping }}</div>
          </div>
        </div>

        <div class="grid-2">
          <div class="panel">
            <h3 class="card-title">CPU</h3>
            <div class="metric-line">
              <span>使用率</span>
              <b>{{ data.cpu.usage_percent }}%</b>
            </div>
            <el-progress :percentage="Number(data.cpu.usage_percent)" :stroke-width="10" :show-text="false" />
            <div class="meta-grid">
              <div><span class="muted">物理核心</span><b>{{ data.cpu.physical }}</b></div>
              <div><span class="muted">逻辑核心</span><b>{{ data.cpu.logical }}</b></div>
              <div><span class="muted">频率</span><b>{{ data.cpu.frequency_mhz || '—' }} MHz</b></div>
              <div><span class="muted">负载</span><b>{{ (data.cpu.load_avg || []).join(' / ') || '—' }}</b></div>
            </div>
          </div>

          <div class="panel">
            <h3 class="card-title">内存</h3>
            <div class="metric-line">
              <span>{{ bytesText(data.memory.used) }} / {{ bytesText(data.memory.total) }}</span>
              <b>{{ data.memory.percent }}%</b>
            </div>
            <el-progress
              :percentage="Number(data.memory.percent)"
              :stroke-width="10"
              :show-text="false"
              :color="data.memory.percent > 85 ? '#ef4444' : '#2563eb'"
            />
            <div class="meta-grid">
              <div><span class="muted">可用</span><b>{{ bytesText(data.memory.available) }}</b></div>
              <div><span class="muted">Swap</span><b>{{ bytesText(data.memory.swap_used) }} / {{ bytesText(data.memory.swap_total) }}</b></div>
            </div>
          </div>
        </div>

        <div class="panel">
          <h3 class="card-title">磁盘</h3>
          <div class="disk-list">
            <div v-for="disk in data.disk.partitions" :key="disk.mountpoint" class="disk-item">
              <div class="disk-head">
                <span><b>{{ disk.mountpoint }}</b> <span class="muted">{{ disk.device }} · {{ disk.fstype }}</span></span>
                <span class="muted">{{ bytesText(disk.used) }} / {{ bytesText(disk.total) }}</span>
              </div>
              <el-progress
                :percentage="Number(disk.percent)"
                :stroke-width="8"
                :show-text="false"
                :color="disk.percent > 85 ? '#ef4444' : '#10b981'"
              />
            </div>
          </div>
        </div>

        <div class="panel">
          <h3 class="card-title">GPU</h3>
          <div v-if="data.gpu.length" class="gpu-grid">
            <div v-for="gpu in data.gpu" :key="gpu.index" class="gpu-card">
              <div class="gpu-name">{{ gpu.name }}</div>
              <div class="gpu-meta">
                <span>显存 {{ gpu.memory_used_mb }} / {{ gpu.memory_total_mb }} MB</span>
                <span>{{ gpu.utilization_percent }}%</span>
              </div>
              <el-progress
                :percentage="Number(gpu.utilization_percent)"
                :stroke-width="8"
                :show-text="false"
                color="#8b5cf6"
              />
              <div class="gpu-meta">
                <span class="muted">显存占用</span>
                <span>{{ gpuPercent(gpu) }}%</span>
              </div>
              <div class="gpu-meta">
                <span class="muted">温度</span>
                <span>{{ gpu.temperature_c }} ℃</span>
              </div>
              <div class="muted">驱动 {{ gpu.driver_version }}</div>
            </div>
          </div>
          <el-empty v-else description="未检测到可用 GPU（或未安装 nvidia-smi）" :image-size="70" />
        </div>

        <div class="grid-2">
          <div class="panel">
            <h3 class="card-title">网络</h3>
            <div class="meta-grid">
              <div><span class="muted">发送</span><b>{{ bytesText(data.network.bytes_sent) }}</b></div>
              <div><span class="muted">接收</span><b>{{ bytesText(data.network.bytes_recv) }}</b></div>
              <div><span class="muted">发送包</span><b>{{ data.network.packets_sent }}</b></div>
              <div><span class="muted">接收包</span><b>{{ data.network.packets_recv }}</b></div>
            </div>
            <div class="iface-list">
              <div v-for="iface in data.network.interfaces" :key="iface.interface + iface.address" class="iface-item">
                <el-tag size="small" effect="plain">{{ iface.interface }}</el-tag>
                <span>{{ iface.address }}</span>
              </div>
            </div>
          </div>

          <div class="panel">
            <h3 class="card-title">Redis / 数据库</h3>
            <div class="dep-block">
              <div class="dep-head">
                <el-tag :type="data.redis.connected ? 'success' : 'danger'" effect="dark">
                  Redis {{ data.redis.connected ? '已连接' : '未连接' }}
                </el-tag>
                <span class="muted">{{ data.redis.host }}:{{ data.redis.port }}</span>
              </div>
              <div v-if="data.redis.connected" class="meta-grid">
                <div><span class="muted">版本</span><b>{{ data.redis.version }}</b></div>
                <div><span class="muted">内存</span><b>{{ data.redis.used_memory_human }}</b></div>
                <div><span class="muted">客户端</span><b>{{ data.redis.connected_clients }}</b></div>
                <div><span class="muted">命中/未命中</span><b>{{ data.redis.keyspace_hits }} / {{ data.redis.keyspace_misses }}</b></div>
                <div><span class="muted">限流后端</span><b>{{ data.redis.rate_limit_backend }}</b></div>
                <div><span class="muted">限流桶</span><b>{{ data.redis.rate_limit_buckets }}</b></div>
              </div>
              <div v-else class="muted">限流已降级为进程内滑动窗口。</div>
            </div>

            <div class="dep-block">
              <div class="dep-head">
                <el-tag :type="data.database.connected ? 'success' : 'danger'" effect="dark">
                  PostgreSQL {{ data.database.connected ? '已连接' : '未连接' }}
                </el-tag>
                <span class="muted">{{ data.database.response_time_ms ?? '—' }} ms</span>
              </div>
              <div class="muted">{{ data.database.target }}</div>
            </div>
          </div>
        </div>

        <div class="muted updated-at">数据时间：{{ formatTime(data.timestamp) }}</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import api from '../utils/api'

const data = ref(null)
const loading = ref(false)
const autoRefresh = ref(true)
let timer = null

async function load() {
  loading.value = true
  try {
    data.value = await api.get('/system/status')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function schedule() {
  if (timer) clearInterval(timer)
  timer = null
  if (autoRefresh.value) timer = setInterval(load, 10000)
}

function bytesText(value) {
  if (value === null || value === undefined) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let num = Number(value)
  let i = 0
  while (num >= 1024 && i < units.length - 1) {
    num /= 1024
    i += 1
  }
  return `${num.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function uptimeText(seconds) {
  const s = Number(seconds || 0)
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  if (days) return `${days} 天 ${hours} 小时`
  if (hours) return `${hours} 小时 ${minutes} 分`
  return `${minutes} 分钟`
}

function gpuPercent(gpu) {
  if (!gpu.memory_total_mb) return 0
  return Math.round((gpu.memory_used_mb / gpu.memory_total_mb) * 100)
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

watch(autoRefresh, schedule)

onMounted(() => {
  load()
  schedule()
})
onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<style scoped>
.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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

.stat-main {
  font-size: 20px;
  font-weight: 700;
  margin: 6px 0 4px;
  word-break: break-all;
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.grid-2 + .grid-2,
.grid-2 + .panel,
.panel + .grid-2 {
  margin-top: 16px;
}

.card-title {
  margin: 0 0 14px;
  font-size: 15px;
}

.metric-line {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 8px;
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 14px;
  font-size: 13px;
}

.meta-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.disk-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.disk-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.gpu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.gpu-card {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gpu-name {
  font-weight: 700;
  font-size: 14px;
}

.gpu-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
}

.iface-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 14px;
  font-size: 13px;
}

.iface-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dep-block + .dep-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--app-border);
}

.dep-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.updated-at {
  margin-top: 14px;
  text-align: right;
}

@media (max-width: 767px) {
  .stat-grid {
    grid-template-columns: 1fr 1fr;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
  .stat-main {
    font-size: 16px;
  }
}
</style>
