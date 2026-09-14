/**
 * SSE 流式问数客户端。
 *
 * 为什么用 fetch + ReadableStream 而不是 EventSource：
 * 问数请求要带 body（问题 + 会话 ID），而 EventSource 只支持 GET。
 */

import type { QueryPayload, StreamEvent } from '../types'
import { BASE_URL } from './client'

export interface StreamHandlers {
  onEvent?: (event: StreamEvent) => void
  onDone?: (payload: QueryPayload, sessionId: number) => void
  onError?: (message: string) => void
}

/** 发起一次流式问数，逐个回调事件。返回一个取消函数。 */
export function streamQuery(
  question: string,
  sessionId: number | null,
  handlers: StreamHandlers = {},
): () => void {
  const controller = new AbortController()

  const run = async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, session_id: sessionId }),
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        handlers.onError?.(`请求失败（HTTP ${response.status}）`)
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE 以空行分隔事件；服务端一条事件只有一个 data: 字段
        let boundary = buffer.indexOf('\n\n')
        while (boundary >= 0) {
          const chunk = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const payload = parseEvent(chunk)
          if (payload) dispatch(payload, handlers)
          boundary = buffer.indexOf('\n\n')
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') return
      handlers.onError?.((error as Error).message || '网络异常，请稍后重试')
    }
  }

  void run()
  return () => controller.abort()
}

function parseEvent(chunk: string): StreamEvent | null {
  const line = chunk
    .split('\n')
    .map((item) => item.trim())
    .find((item) => item.startsWith('data:'))
  if (!line) return null
  const raw = line.slice(5).trim()
  if (!raw) return null
  try {
    return JSON.parse(raw) as StreamEvent
  } catch {
    return null
  }
}

function dispatch(event: StreamEvent, handlers: StreamHandlers) {
  handlers.onEvent?.(event)
  if (event.type === 'done') {
    handlers.onDone?.(event.message, event.session_id)
  } else if (event.type === 'error') {
    handlers.onError?.(event.message)
  }
}
