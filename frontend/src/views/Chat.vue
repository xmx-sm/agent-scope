<template>
  <div class="chat-page">
    <aside class="conv-panel" :class="{ 'conv-mobile': isMobile, open: convOpen }">
      <div class="conv-head">
        <span>会话</span>
        <el-button size="small" type="primary" :icon="Plus" @click="newConversation">新建</el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in filteredConversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === currentId }"
          @click="selectConversation(conv)"
        >
          <div class="conv-title">
            <span class="conv-name">{{ conv.title || '新会话' }}</span>
            <el-tag v-if="originLabel(conv)" size="small" effect="plain" class="conv-origin">
              {{ originLabel(conv) }}
            </el-tag>
          </div>
          <div class="conv-actions">
            <el-button text size="small" :icon="Edit" @click.stop="renameConversation(conv)" />
            <el-button text size="small" :icon="Delete" @click.stop="removeConversation(conv)" />
          </div>
        </div>
        <el-empty v-if="!filteredConversations.length" description="暂无会话" :image-size="60" />
      </div>
    </aside>

    <section class="chat-main">
      <div class="chat-tabs">
        <button
          v-for="tab in CHAT_TABS"
          :key="tab.value"
          type="button"
          class="chat-tab"
          :class="{ active: originFilter === tab.value }"
          @click="switchOrigin(tab.value)"
        >
          {{ tab.label }}
          <span v-if="tabCount(tab.value)" class="chat-tab-count">{{ tabCount(tab.value) }}</span>
        </button>
      </div>

      <header class="chat-head">
        <el-button v-if="isMobile" text circle :icon="Menu" @click="convOpen = !convOpen" />
        <div class="chat-title">{{ currentConversation?.title || 'AI 对话' }}</div>
        <el-tag v-if="currentOrigin" size="small" effect="plain">{{ currentOrigin }}</el-tag>
        <el-tag v-if="stats" size="small" effect="plain">Tokens {{ stats.total_tokens }}</el-tag>
        <el-tag size="small" effect="plain">{{ modelLabel }}</el-tag>
      </header>

      <div ref="listRef" class="message-list">
        <div v-if="!messages.length" class="chat-empty">
          <el-icon :size="40"><ChatDotRound /></el-icon>
          <p>开始一段新对话</p>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
          <div class="bubble">
            <div v-if="msg.reasoning" class="reasoning">
              <el-collapse>
                <el-collapse-item title="思考过程" name="r">
                  <pre>{{ msg.reasoning }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
            <MarkdownView v-if="msg.content" :content="msg.content" />
            <div v-if="msg.content && !msg.streaming" class="msg-actions">
              <el-button
                v-if="msg.role === 'assistant'"
                text
                size="small"
                @click="toggleSpeak(msg)"
              >{{ speakingId === msg.id ? '停止朗读' : '朗读' }}</el-button>
              <el-button
                v-if="!String(msg.id).startsWith('user-') && !String(msg.id).startsWith('stream-')"
                text
                size="small"
                @click="createBranch(msg)"
              >分支</el-button>
            </div>
            <div v-if="msg.attachments?.length" class="msg-attachments">
              <el-tag v-for="file in msg.attachments" :key="file.id" size="small" effect="plain">
                {{ file.filename }}
              </el-tag>
            </div>
            <div v-if="toolList(msg).length" class="tool-events">
              <el-collapse>
                <el-collapse-item :title="`工具调用（${toolList(msg).length}）`" name="t">
                  <div v-for="(tool, i) in toolList(msg)" :key="i" class="tool-item">
                    <el-tag size="small" :type="tool.status === 'success' ? 'success' : 'info'">
                      {{ tool.name }}
                    </el-tag>
                    <pre class="tool-output">{{ tool.output }}</pre>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
        </div>
        <div v-if="streaming && !streamText" class="message assistant">
          <div class="bubble typing">正在生成…</div>
        </div>
      </div>

      <div v-if="pendingAttachments.length" class="pending-attachments">
        <el-tag
          v-for="file in pendingAttachments"
          :key="file.id"
          closable
          size="small"
          @close="removePending(file.id)"
        >
          {{ file.filename }}
        </el-tag>
      </div>
      <div class="composer">
        <input ref="fileInput" type="file" multiple hidden @change="onFiles" />
        <el-button :icon="Paperclip" circle :loading="uploading" @click="fileInput.click()" />
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          :disabled="streaming"
          @keydown.enter.exact.prevent="send"
        />
        <el-button v-if="streaming" type="danger" :icon="VideoPause" @click="stop">停止</el-button>
        <el-button v-else type="primary" :icon="Promotion" :disabled="!input.trim()" @click="send">
          发送
        </el-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  Delete,
  Edit,
  Menu,
  Plus,
  Paperclip,
  Promotion,
  VideoPause
} from '@element-plus/icons-vue'
import { useChatStore } from '../stores/chat'
import MarkdownView from '../components/MarkdownView.vue'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const convOpen = ref(false)
const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const {
  conversations,
  currentId,
  messages,
  stats,
  streaming,
  streamText,
  currentConversation
} = storeToRefs(chat)

const speakingId = ref('')
let audioPlayer = null
const input = ref('')
const fileInput = ref(null)
const uploading = ref(false)
const pendingAttachments = ref([])
const listRef = ref(null)
const originFilter = ref('chat')

const CHAT_TABS = [
  { label: 'AI 对话', value: 'chat' },
  { label: 'A2A 对话', value: 'a2a' },
  { label: '超级智能体', value: 'super' },
  { label: '定时任务', value: 'cron' }
]

const ORIGIN_LABELS = {
  super_main: '超级·主',
  super_sub: '超级·子',
  a2a: 'A2A',
  cron: '定时',
  branch: '分支'
}

function normalizeOriginFilter(value) {
  const text = String(value || 'chat')
  if (text === 'all' || text === 'branch') return 'chat'
  return ['chat', 'a2a', 'super', 'cron'].includes(text) ? text : 'chat'
}

function originLabel(conv) {
  if (!conv?.origin) return ''
  return ORIGIN_LABELS[conv.origin] || conv.origin
}

const filteredConversations = computed(() => {
  const origin = originFilter.value
  if (origin === 'chat') {
    return conversations.value.filter((item) => !item.origin || item.origin === 'branch')
  }
  if (origin === 'super') {
    return conversations.value.filter((item) => ['super_main', 'super_sub'].includes(item.origin))
  }
  return conversations.value.filter((item) => item.origin === origin)
})

function tabCount(value) {
  if (value === 'chat') {
    return conversations.value.filter((item) => !item.origin || item.origin === 'branch').length
  }
  if (value === 'super') {
    return conversations.value.filter((item) => ['super_main', 'super_sub'].includes(item.origin)).length
  }
  return conversations.value.filter((item) => item.origin === value).length
}

const currentOrigin = computed(() => originLabel(currentConversation.value))

const modelLabel = computed(() => 'AI')
const toolList = (msg) => chat.toolList(msg)

function onResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) convOpen.value = false
}

async function renameConversation(conv) {
  try {
    const { value } = await ElMessageBox.prompt('新的会话标题', '重命名', {
      inputValue: conv.title || '',
      inputValidator: (value) => Boolean(value && value.trim()) || '标题不能为空'
    })
    await chat.renameConversation(conv.id, value.trim())
  } catch {
    /* ignore */
  }
}

async function loadConversations() {
  originFilter.value = normalizeOriginFilter(route.query.origin)
  const wanted = route.query.conversation
  await chat.loadConversations(wanted ? String(wanted) : '')
  await ensureFilteredConversation()
  await chat.resumeIfNeeded()
  scrollToBottom()
}

async function ensureFilteredConversation() {
  if (streaming.value) return
  const list = filteredConversations.value
  if (!list.length || list.some((item) => item.id === currentId.value)) return
  try {
    await chat.selectConversation(list[0].id)
    scrollToBottom()
  } catch {
    /* ignore */
  }
}

function switchOrigin(value) {
  if (originFilter.value === value) return
  originFilter.value = value
  const query = { ...route.query }
  delete query.conversation
  if (value === 'chat') delete query.origin
  else query.origin = value
  router.replace({ path: route.path, query })
}

async function selectConversation(conv) {
  try {
    await chat.selectConversation(conv.id)
    convOpen.value = false
    scrollToBottom()
    await chat.resumeIfNeeded()
  } catch (error) {
    ElMessage.warning(error.message || '切换会话失败')
  }
}

async function newConversation() {
  try {
    await chat.newConversation()
    originFilter.value = 'chat'
    convOpen.value = false
  } catch (error) {
    ElMessage.warning(error.message || '新建会话失败')
  }
}

async function removeConversation(conv) {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await chat.removeConversation(conv.id)
  } catch (error) {
    ElMessage.warning(error.message || '删除会话失败')
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

async function onFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024) {
        ElMessage.warning(`${file.name} 超过 20MB`)
        continue
      }
      const form = new FormData()
      form.append('file', file)
      const data = await api.post('/agent/attachments', form)
      pendingAttachments.value.push(data)
    }
  } catch {
    /* ignore */
  } finally {
    uploading.value = false
  }
}

function removePending(id) {
  pendingAttachments.value = pendingAttachments.value.filter((file) => file.id !== id)
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!currentId.value) {
    try {
      await chat.newConversation()
    } catch (error) {
      ElMessage.warning(error.message || '新建会话失败')
      return
    }
  }
  if (!currentId.value) return
  const attachments = [...pendingAttachments.value]
  input.value = ''
  pendingAttachments.value = []
  scrollToBottom()
  await chat.send({
    text,
    attachmentIds: attachments.map((file) => file.id),
    attachments
  })
}

function stop() {
  chat.stop()
}

async function createBranch(msg) {
  try {
    const conv = await api.post(`/agent/conversations/${currentId.value}/branch`, {
      message_id: msg.id
    })
    ElMessage.success('分支已创建')
    router.push({ path: '/chat', query: { conversation: conv.id } })
  } catch {
    /* ignore */
  }
}

function cleanSpeech(text) {
  return String(text || '')
    .replace(/```[\s\S]*?```/g, ' 代码块 ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[#>*_~\-]{1,}/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function stopSpeak() {
  if (audioPlayer) {
    audioPlayer.pause()
    audioPlayer = null
  }
  speakingId.value = ''
}

async function toggleSpeak(msg) {
  if (speakingId.value === msg.id) {
    stopSpeak()
    return
  }
  const text = cleanSpeech(msg.content)
  if (!text) return
  stopSpeak()
  speakingId.value = msg.id
  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE || '/api'}/agent/tts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`
      },
      body: JSON.stringify({ text: text.slice(0, 2000) })
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.msg || `HTTP ${response.status}`)
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    audioPlayer = new Audio(url)
    audioPlayer.onended = () => {
      URL.revokeObjectURL(url)
      stopSpeak()
    }
    await audioPlayer.play()
  } catch (error) {
    stopSpeak()
    ElMessage.error(error.message || '语音合成失败')
  }
}

watch(
  () => [messages.value.length, streamText.value, streaming.value],
  () => scrollToBottom()
)

watch(
  () => route.query.origin,
  (value) => {
    originFilter.value = normalizeOriginFilter(value)
  }
)

watch(originFilter, () => {
  ensureFilteredConversation()
})

watch(
  () => route.query.conversation,
  async (id) => {
    if (!id || id === currentId.value || streaming.value) return
    try {
      await chat.selectConversation(String(id))
      scrollToBottom()
      await chat.resumeIfNeeded()
    } catch {
      /* ignore */
    }
  }
)

onMounted(async () => {
  window.addEventListener('resize', onResize)
  await loadConversations()
  chat.loadStats()
})

onBeforeUnmount(() => {
  // 只清理页面级资源；生成任务由 Pinia store 托管，切换页面不会中断。
  window.removeEventListener('resize', onResize)
  stopSpeak()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 58px);
  background: var(--app-bg);
}

.conv-panel {
  width: 252px;
  background: #fff;
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  flex: none;
}

.conv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--app-border);
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conv-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 4px;
}

.conv-item:hover {
  background: #f3f4f6;
}

.conv-item.active {
  background: #eff6ff;
}

.conv-title {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 22px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.conv-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-origin {
  flex: none;
}

.conv-actions {
  position: absolute;
  right: 4px;
  top: 4px;
  opacity: 0;
  display: flex;
}

.conv-item:hover .conv-actions {
  opacity: 1;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 16px 0;
  background: #fff;
  border-bottom: 1px solid var(--app-border);
  overflow-x: auto;
}

.chat-tab {
  padding: 8px 12px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--app-muted);
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}

.chat-tab.active {
  color: var(--app-primary);
  border-bottom-color: var(--app-primary);
  font-weight: 600;
}

.chat-tab-count {
  margin-left: 4px;
  font-size: 11px;
  color: #6b7280;
}

.chat-head {
  height: 52px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid var(--app-border);
}

.chat-title {
  flex: 1;
  font-weight: 600;
  font-size: 14px;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.chat-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--app-muted);
  gap: 8px;
}

.message {
  display: flex;
  margin-bottom: 14px;
}

.message.user {
  justify-content: flex-end;
}

.bubble {
  max-width: min(760px, 86%);
  background: #fff;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.7;
}

.message.user .bubble {
  background: var(--app-primary);
  color: #fff;
  border-color: var(--app-primary);
}

.message.user .bubble :deep(.markdown-body) {
  color: #fff;
}

.message.user .bubble :deep(.markdown-body a) {
  color: #dbeafe;
}

.message.user .bubble :deep(.markdown-body code) {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.message.user .bubble :deep(.markdown-body blockquote) {
  border-left-color: rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.12);
  color: #f3f4f6;
}

.reasoning {
  margin-bottom: 8px;
}

.reasoning pre,
.tool-output {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  margin: 6px 0 0;
}

.tool-events {
  margin-top: 8px;
}

.tool-item {
  margin-bottom: 8px;
}

.typing {
  color: var(--app-muted);
}

.pending-attachments {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 16px 0;
  background: #fff;
}

.msg-attachments {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.composer {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid var(--app-border);
  align-items: flex-end;
}

.composer .el-input {
  flex: 1;
}

@media (max-width: 767px) {
  .conv-panel.conv-mobile {
    position: fixed;
    left: 0;
    top: 58px;
    bottom: 0;
    z-index: 30;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: 4px 0 16px rgba(0, 0, 0, 0.1);
  }
  .conv-panel.conv-mobile.open {
    transform: translateX(0);
  }
  .message-list {
    padding: 12px;
  }
  .bubble {
    max-width: 92%;
  }
  .composer {
    padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
  }
}
</style>

<style scoped>
.msg-actions { margin-top: 4px; }
</style>
