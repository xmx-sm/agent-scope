<template>
  <div class="chat-page">
    <aside class="conv-panel" :class="{ 'conv-mobile': isMobile, open: convOpen }">
      <div class="conv-head">
        <span>会话</span>
        <el-button size="small" type="primary" :icon="Plus" @click="newConversation">新建</el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === currentId }"
          @click="selectConversation(conv)"
        >
          <div class="conv-title">{{ conv.title || '新会话' }}</div>
          <div class="conv-actions">
            <el-button text size="small" :icon="Edit" @click.stop="renameConversation(conv)" />
            <el-button text size="small" :icon="Delete" @click.stop="removeConversation(conv)" />
          </div>
        </div>
        <el-empty v-if="!conversations.length" description="暂无会话" :image-size="60" />
      </div>
    </aside>

    <section class="chat-main">
      <header class="chat-head">
        <el-button v-if="isMobile" text circle :icon="Menu" @click="convOpen = !convOpen" />
        <div class="chat-title">{{ currentConversation?.title || 'AI 对话' }}</div>
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
            <pre class="content">{{ msg.content }}</pre>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
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
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const convOpen = ref(false)
const conversations = ref([])
const currentId = ref('')
const messages = ref([])
const stats = ref(null)
const input = ref('')
const fileInput = ref(null)
const uploading = ref(false)
const pendingAttachments = ref([])
const streaming = ref(false)
const streamText = ref('')
const listRef = ref(null)
let controller = null

const currentConversation = computed(() =>
  conversations.value.find((item) => item.id === currentId.value)
)
const modelLabel = computed(() => 'AI')
const toolList = (msg) => {
  try {
    return JSON.parse(msg.tool_events || '[]')
  } catch {
    return []
  }
}

function onResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) convOpen.value = false
}

async function loadStats() {
  try {
    stats.value = await api.get('/agent/stats')
  } catch {
    /* ignore */
  }
}

async function renameConversation(conv) {
  try {
    const { value } = await ElMessageBox.prompt('新的会话标题', '重命名', {
      inputValue: conv.title || '',
      inputValidator: (value) => Boolean(value && value.trim()) || '标题不能为空'
    })
    const data = await api.patch(`/agent/conversations/${conv.id}`, { title: value.trim() })
    conv.title = data.title
    await loadConversations()
  } catch {
    /* ignore */
  }
}

async function loadConversations() {
  try {
    conversations.value = await api.get('/agent/conversations')
    if (!currentId.value && conversations.value.length) {
      await selectConversation(conversations.value[0])
    }
  } catch {
    /* ignore */
  }
}

async function selectConversation(conv) {
  currentId.value = conv.id
  convOpen.value = false
  try {
    messages.value = await api.get(`/agent/conversations/${conv.id}/messages`)
    scrollToBottom()
  } catch {
    /* ignore */
  }
}

async function newConversation() {
  try {
    const conv = await api.post('/agent/conversations', { title: '新会话' })
    conversations.value.unshift(conv)
    currentId.value = conv.id
    messages.value = []
    convOpen.value = false
  } catch {
    /* ignore */
  }
}

async function removeConversation(conv) {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/agent/conversations/${conv.id}`)
    conversations.value = conversations.value.filter((item) => item.id !== conv.id)
    if (currentId.value === conv.id) {
      currentId.value = conversations.value[0]?.id || ''
      messages.value = []
      if (currentId.value) await selectConversation(conversations.value[0])
    }
  } catch {
    /* ignore */
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

function appendDelta(text) {
  streamText.value += text
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant' && last.streaming) {
    last.content = streamText.value
  } else {
    messages.value.push({
      id: `stream-${Date.now()}`,
      role: 'assistant',
      content: streamText.value,
      reasoning: '',
      tool_events: '[]',
      streaming: true
    })
  }
  scrollToBottom()
}

function handleEvent(event, data) {
  if (event === 'text_delta') appendDelta(data.text || '')
  else if (event === 'reasoning_delta') {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.streaming) {
      last.reasoning = (last.reasoning || '') + (data.text || '')
    }
  } else if (event === 'tool_result') {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      const tools = toolList(last)
      tools.push(data)
      last.tool_events = JSON.stringify(tools)
    }
  } else if (event === 'error') {
    ElMessage.error(data.error || '生成失败')
  } else if (event === 'done') {
    streamText.value = data.content || streamText.value
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!currentId.value) await newConversation()
  if (!currentId.value) return
  input.value = ''
  pendingAttachments.value = []
  streaming.value = true
  streamText.value = ''
  messages.value.push({
    id: `user-${Date.now()}`,
    role: 'user',
    content: text,
    reasoning: '',
    tool_events: '[]',
    attachments: [...pendingAttachments.value]
  })
  const streamingMsg = {
    id: `stream-${Date.now()}`,
    role: 'assistant',
    content: '',
    reasoning: '',
    tool_events: '[]',
    streaming: true
  }
  messages.value.push(streamingMsg)
  scrollToBottom()

  controller = new AbortController()
  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE || '/api'}/agent/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`
      },
      body: JSON.stringify({
        conversation_id: currentId.value,
        content: text,
        attachment_ids: pendingAttachments.value.map((file) => file.id)
      }),
      signal: controller.signal
    })
    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        if (!frame.trim()) continue
        let event = 'message'
        let data = {}
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) {
            try {
              data = JSON.parse(line.slice(5).trim())
            } catch {
              data = {}
            }
          }
        }
        handleEvent(event, data)
      }
    }
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) {
      last.content = streamText.value
      last.streaming = false
    }
    await loadConversations()
    await loadStats()
    await selectConversation({ id: currentId.value })
  } catch (error) {
    if (error.name !== 'AbortError') ElMessage.error(error.message || '发送失败')
  } finally {
    streaming.value = false
    controller = null
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) last.streaming = false
  }
}

function stop() {
  if (controller) controller.abort()
  streaming.value = false
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  loadConversations()
  loadStats()
})
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
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

.content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.message.user .content {
  color: #fff;
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
