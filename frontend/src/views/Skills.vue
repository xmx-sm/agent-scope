<template>
  <div class="page">
    <h2 class="page-title">Skills</h2>
    <p class="page-desc">上传技能压缩包（根目录或单层子目录包含 SKILL.md），启用后注入 Agent</p>

    <div class="panel" v-loading="loading">
      <div class="toolbar">
        <input ref="fileInput" type="file" accept=".zip" hidden @change="upload" />
        <el-button type="primary" :icon="Upload" :loading="uploading" @click="fileInput.click()">
          上传技能包
        </el-button>
        <span class="muted">ZIP，≤20MB，包含 SKILL.md</span>
      </div>

      <div class="skill-list">
        <div v-for="skill in skills" :key="skill.id" class="skill-card">
          <div class="skill-main">
            <div class="skill-name">{{ skill.name }}</div>
            <div class="muted">{{ skill.description || '暂无描述' }}</div>
          </div>
          <div class="skill-actions">
            <el-switch
              :model-value="skill.is_active"
              :loading="savingId === skill.id"
              @change="(checked) => toggle(skill, checked)"
            />
            <el-button text type="danger" :icon="Delete" @click="remove(skill)" />
          </div>
        </div>
        <el-empty v-if="!skills.length && !loading" description="暂无技能" :image-size="70" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Upload } from '@element-plus/icons-vue'
import api from '../utils/api'

const loading = ref(false)
const uploading = ref(false)
const savingId = ref('')
const skills = ref([])
const fileInput = ref(null)

async function load() {
  loading.value = true
  try {
    skills.value = await api.get('/agent/skills')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('name', file.name.replace(/\.zip$/i, ''))
    await api.post('/agent/skills/upload', form)
    ElMessage.success('技能已上传')
    await load()
  } catch {
    /* ignore */
  } finally {
    uploading.value = false
  }
}

async function toggle(skill, checked) {
  savingId.value = skill.id
  try {
    const data = await api.patch(`/agent/skills/${skill.id}`, { is_active: checked })
    skill.is_active = data.is_active
  } catch {
    /* ignore */
  } finally {
    savingId.value = ''
  }
}

async function remove(skill) {
  try {
    await ElMessageBox.confirm(`确定删除技能「${skill.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/skills/${skill.id}`)
    ElMessage.success('技能已删除')
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
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px 14px;
}

.skill-name {
  font-weight: 600;
  margin-bottom: 4px;
}

.skill-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
