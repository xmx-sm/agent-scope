import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const apiBase = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`

function authHeaders(extra = {}) {
  return {
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    ...extra
  }
}

/**
 * 对话运行时状态放在 Pinia 里，路由切换（Chat 组件卸载再挂载）时不会中断：
 * 生成任务继续写 store，回到对话页即可看到最新内容。
 */
export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const currentId = ref('')
  const messages = ref([])
  const stats = ref(null)
  const streaming = ref(false)
  const streamText = ref('')

  const currentConversation = computed(() =>
    conversations.value.find((item) => item.id === currentId.value)
  )

  let controller = null
  let suppressResumeError = false
  let resumeNoTask = false

  function toolList(msg) {
    try {
      return JSON.parse(msg.tool_events || '[]')
    } catch {
      return []
    }
  }

  function markLastDone() {
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) {
      if (streamText.value) last.content = streamText.value
      last.streaming = false
    }
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
      const message = String(data.error || '生成失败')
      if (suppressResumeError && message.includes('没有可续传')) {
        resumeNoTask = true
        return
      }
      ElMessage.error(message)
    } else if (event === 'done') {
      streamText.value = data.content || streamText.value
      // 立即把最终结果写回当前气泡，避免等待刷新接口造成“完成后不渲染”。
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.content = streamText.value
        last.streaming = false
        if (data.message_id) last.id = data.message_id
      }
    }
  }

  async function readStream(response) {
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
  }

  async function refreshConversations() {
    try {
      conversations.value = await api.get('/agent/conversations')
    } catch {
      /* ignore */
    }
  }

  async function finishStream() {
    markLastDone()
    await loadStats()
    // 只刷新会话列表（标题/排序），不回读消息，避免请求时序或缓存导致最终消息被旧数据覆盖。
    await refreshConversations()
  }

  async function runResume({ silentNoTask = false } = {}) {
    suppressResumeError = silentNoTask
    resumeNoTask = false
    try {
      const response = await fetch(`${apiBase}/agent/chat/resume/${currentId.value}`, {
        headers: authHeaders()
      })
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
      await readStream(response)
      if (resumeNoTask) return false
      await finishStream()
      return true
    } finally {
      suppressResumeError = false
    }
  }

  async function send({ text, attachmentIds = [], attachments = [] }) {
    if (streaming.value || !currentId.value) return
    streaming.value = true
    streamText.value = ''
    messages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      reasoning: '',
      tool_events: '[]',
      attachments
    })
    messages.value.push({
      id: `stream-${Date.now()}`,
      role: 'assistant',
      content: '',
      reasoning: '',
      tool_events: '[]',
      streaming: true
    })

    controller = new AbortController()
    try {
      const response = await fetch(`${apiBase}/agent/chat/stream`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          conversation_id: currentId.value,
          content: text,
          attachment_ids: attachmentIds
        }),
        signal: controller.signal
      })
      if (!response.ok || !response.body) {
        let message = `HTTP ${response.status}`
        try {
          const payload = await response.json()
          message = payload.msg || message
        } catch {
          /* 非 JSON 错误保留状态码 */
        }
        const error = new Error(message)
        error.status = response.status
        throw error
      }
      await readStream(response)
      await finishStream()
    } catch (error) {
      if (error.name === 'AbortError') {
        ElMessage.info('已停止生成')
      } else if (error.status === 429 || error.status === 409) {
        ElMessage.warning(error.message || '当前对话繁忙，请稍后重试')
      } else {
        ElMessage.warning('连接中断，正在尝试续传…')
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          last.content = ''
          last.reasoning = ''
          last.tool_events = '[]'
        }
        streamText.value = ''
        try {
          await runResume()
          ElMessage.success('已续传')
        } catch (resumeError) {
          ElMessage.error(resumeError.message || '续传失败，请刷新页面查看已生成内容')
        }
      }
    } finally {
      streaming.value = false
      controller = null
      markLastDone()
    }
  }

  /**
   * 页面刷新/重新进入时，如果最后一条是用户消息（说明上一轮还没落库），
   * 尝试从后端重放进行中的生成任务。
   */
  async function resumeIfNeeded() {
    if (streaming.value || !currentId.value) return false
    const last = messages.value[messages.value.length - 1]
    if (!last || last.role !== 'user') return false

    streaming.value = true
    streamText.value = ''
    const placeholder = {
      id: `stream-${Date.now()}`,
      role: 'assistant',
      content: '',
      reasoning: '',
      tool_events: '[]',
      streaming: true
    }
    messages.value.push(placeholder)
    let resumed = false
    try {
      resumed = await runResume({ silentNoTask: true })
    } catch {
      resumed = false
    } finally {
      streaming.value = false
      if (!resumed && !placeholder.content) {
        const index = messages.value.indexOf(placeholder)
        if (index >= 0) messages.value.splice(index, 1)
      } else {
        markLastDone()
      }
    }
    return resumed
  }

  async function loadStats() {
    try {
      stats.value = await api.get('/agent/stats')
    } catch {
      /* ignore */
    }
  }

  async function loadConversations(preferredId = '') {
    try {
      conversations.value = await api.get('/agent/conversations')
    } catch {
      return
    }
    // 生成过程中只刷新列表，不重新拉取消息，避免覆盖正在流式输出的内容。
    if (streaming.value && currentId.value) return

    const target =
      conversations.value.find((item) => item.id === preferredId) ||
      conversations.value.find((item) => item.id === currentId.value) ||
      conversations.value[0]
    if (target) await selectConversation(target.id)
  }

  async function selectConversation(id) {
    if (streaming.value && id !== currentId.value) {
      throw new Error('正在生成，请先停止或等待完成')
    }
    currentId.value = id
    try {
      messages.value = await api.get(`/agent/conversations/${id}/messages`, {
        params: { _t: Date.now() }
      })
    } catch {
      /* ignore */
    }
  }

  async function newConversation() {
    if (streaming.value) throw new Error('正在生成，请先停止或等待完成')
    const conv = await api.post('/agent/conversations', { title: '新会话' })
    conversations.value.unshift(conv)
    currentId.value = conv.id
    messages.value = []
    streamText.value = ''
    return conv
  }

  async function removeConversation(id) {
    if (streaming.value && id === currentId.value) {
      throw new Error('正在生成，请先停止或等待完成')
    }
    await api.delete(`/agent/conversations/${id}`)
    conversations.value = conversations.value.filter((item) => item.id !== id)
    if (currentId.value === id) {
      currentId.value = ''
      messages.value = []
      const next = conversations.value[0]
      if (next) await selectConversation(next.id)
    }
  }

  async function renameConversation(id, title) {
    const data = await api.patch(`/agent/conversations/${id}`, { title })
    const conv = conversations.value.find((item) => item.id === id)
    if (conv) conv.title = data.title
  }

  function stop() {
    if (controller) controller.abort()
    streaming.value = false
    markLastDone()
  }

  function reset() {
    if (controller) controller.abort()
    controller = null
    streamText.value = ''
    streaming.value = false
    messages.value = []
    conversations.value = []
    currentId.value = ''
    stats.value = null
  }

  return {
    conversations,
    currentId,
    messages,
    stats,
    streaming,
    streamText,
    currentConversation,
    toolList,
    send,
    stop,
    reset,
    loadStats,
    loadConversations,
    selectConversation,
    newConversation,
    removeConversation,
    renameConversation,
    resumeIfNeeded
  }
})
