/** 问答会话 store：SSE 流式消息、会话切换与历史。 */

import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as chatApi from '@/api/chat'
import type { Citation, ConversationOut } from '@/api/types'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  streaming: boolean
}

function toMessage(item: {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
}): ChatMessage {
  return {
    id: item.id,
    role: item.role,
    content: item.content,
    citations: item.citations ?? [],
    streaming: false,
  }
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationOut[]>([])
  const messages = ref<ChatMessage[]>([])
  const currentConversationId = ref<number | null>(null)
  const streaming = ref(false)

  let controller: AbortController | null = null

  async function loadConversations(): Promise<void> {
    const page = await chatApi.listHistory(1, 50)
    conversations.value = page.items
  }

  async function loadConversation(conversationId: number): Promise<void> {
    const detail = await chatApi.getHistoryDetail(conversationId)
    currentConversationId.value = conversationId
    messages.value = detail.messages.map(toMessage)
  }

  function startNewConversation(): void {
    currentConversationId.value = null
    messages.value = []
  }

  async function ask(kbId: number, question: string, topK?: number): Promise<void> {
    if (streaming.value) {
      return
    }

    messages.value.push({
      id: -Date.now(),
      role: 'user',
      content: question,
      citations: [],
      streaming: false,
    })
    messages.value.push({
      id: -1,
      role: 'assistant',
      content: '',
      citations: [],
      streaming: true,
    })

    // 取响应式代理，直接改原对象不会触发视图更新
    const assistant = messages.value[messages.value.length - 1]
    streaming.value = true
    controller = new AbortController()

    try {
      await chatApi.askStream(
        {
          kb_id: kbId,
          question,
          conversation_id: currentConversationId.value,
          top_k: topK,
        },
        {
          onDelta: (delta) => {
            assistant.content += delta
          },
          onDone: (payload) => {
            assistant.id = payload.message_id
            assistant.citations = payload.citations
            currentConversationId.value = payload.conversation_id
          },
          onError: (message) => {
            assistant.content += `\n\n> 生成失败：${message}`
          },
        },
        controller.signal,
      )
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        assistant.content += `\n\n> 请求异常：${(error as Error).message}`
      }
    } finally {
      assistant.streaming = false
      streaming.value = false
      controller = null
      await loadConversations().catch(() => undefined)
    }
  }

  function stopStreaming(): void {
    controller?.abort()
  }

  return {
    conversations,
    messages,
    currentConversationId,
    streaming,
    loadConversations,
    loadConversation,
    startNewConversation,
    ask,
    stopStreaming,
  }
})
