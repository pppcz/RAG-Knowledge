/** 问答接口：SSE 流式解析（EventSource 无法带 Authorization，改用 fetch + ReadableStream）。 */

import { apiBaseUrl, TOKEN_KEY } from './http'
import type {
  AskDonePayload,
  ConversationDetail,
  ConversationOut,
  PageResult,
} from './types'

export interface AskPayload {
  kb_id: number
  question: string
  conversation_id?: number | null
  top_k?: number
}

export interface AskHandlers {
  onDelta: (delta: string) => void
  onDone: (payload: AskDonePayload) => void
  onError: (message: string) => void
}

interface ParsedEvent {
  event: string
  data: string
}

function parseEventBlock(raw: string): ParsedEvent | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }
  return { event, data: dataLines.join('\n') }
}

/** 发起流式问答；返回中断函数所需的 AbortSignal。 */
export async function askStream(
  payload: AskPayload,
  handlers: AskHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${apiBaseUrl()}/chat/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      if (body?.message) {
        message = body.message as string
      }
    } catch {
      // 非 JSON 响应，保留默认提示
    }
    handlers.onError(message)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    handlers.onError('当前浏览器不支持流式响应')
    return
  }

  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  const separator = /\r?\n\r?\n/

  const dispatch = (block: string): void => {
    const parsed = parseEventBlock(block)
    if (!parsed) {
      return
    }
    let data: unknown
    try {
      data = JSON.parse(parsed.data)
    } catch {
      return
    }

    if (parsed.event === 'message') {
      const delta = (data as { delta?: string }).delta ?? ''
      if (delta) {
        handlers.onDelta(delta)
      }
    } else if (parsed.event === 'done') {
      handlers.onDone(data as AskDonePayload)
    } else if (parsed.event === 'error') {
      handlers.onError((data as { message?: string }).message ?? '生成回答失败')
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })

      let match = separator.exec(buffer)
      while (match) {
        const block = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)
        dispatch(block)
        match = separator.exec(buffer)
      }
    }

    if (buffer.trim()) {
      dispatch(buffer)
    }
  } finally {
    reader.releaseLock()
  }
}

export async function listHistory(
  page = 1,
  pageSize = 20,
): Promise<PageResult<ConversationOut>> {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(
    `${apiBaseUrl()}/chat/history?page=${page}&page_size=${pageSize}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  )
  if (!response.ok) {
    throw new Error(`加载会话历史失败（${response.status}）`)
  }
  return (await response.json()) as PageResult<ConversationOut>
}

export async function getHistoryDetail(conversationId: number): Promise<ConversationDetail> {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${apiBaseUrl()}/chat/history/${conversationId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new Error(`加载会话详情失败（${response.status}）`)
  }
  return (await response.json()) as ConversationDetail
}
