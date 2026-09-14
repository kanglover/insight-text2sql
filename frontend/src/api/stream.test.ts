import { describe, expect, it, vi } from 'vitest'
import { streamQuery } from './stream'
import { makePayload, toSse } from '../test/fixtures'
import type { QueryPayload, StreamEvent } from '../types'

/** 用给定的分片顺序模拟服务端流式响应。 */
function streamResponse(chunks: string[], status = 200) {
  const encoder = new TextEncoder()
  let index = 0
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close()
        return
      }
      controller.enqueue(encoder.encode(chunks[index]))
      index += 1
    },
  })
  return { ok: status < 400, status, body } as unknown as Response
}

function stubFetch(result: unknown) {
  const fn = vi.fn().mockResolvedValue(result)
  vi.stubGlobal('fetch', fn)
  return fn
}

const DONE_EVENT: StreamEvent = { type: 'done', message: makePayload(), session_id: 7 }

describe('streamQuery', () => {
  it('逐条派发事件，并在 done 时回调完整载荷', async () => {
    const events: StreamEvent[] = [
      { type: 'progress', step: '问题解析', node: 'parse', status: 'running' },
      { type: 'keywords', keywords: ['收入'] },
      {
        type: 'result',
        columns: ['org_name'],
        rows: [['北京']],
        row_count: 1,
        duration_ms: 12,
      },
      DONE_EVENT,
    ]
    stubFetch(streamResponse([toSse(events)]))

    const onEvent = vi.fn()
    const onDone = vi.fn<(payload: QueryPayload, sessionId: number) => void>()
    streamQuery('各经营单元的收入', 3, { onEvent, onDone })

    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(onEvent).toHaveBeenCalledTimes(4)
    expect(onEvent.mock.calls[0][0]).toMatchObject({ type: 'progress' })
    expect(onDone.mock.calls[0][1]).toBe(7)
    expect(onDone.mock.calls[0][0].row_count).toBe(2)
  })

  it('请求体带上问题与会话 ID', async () => {
    const fetchMock = stubFetch(streamResponse([toSse([DONE_EVENT])]))
    streamQuery('收入情况', 42, {})
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/chat/stream')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ question: '收入情况', session_id: 42 })
  })

  it('按空行切分，一个分片里含多条事件也能全部解析', async () => {
    const events: StreamEvent[] = [
      { type: 'keywords', keywords: ['收入'] },
      { type: 'trace', nodes: ['parse', 'recall'] },
      DONE_EVENT,
    ]
    stubFetch(streamResponse([toSse(events)]))

    const onEvent = vi.fn()
    streamQuery('q', null, { onEvent })
    await vi.waitFor(() => expect(onEvent).toHaveBeenCalledTimes(3))
  })

  it('事件被切在两个分片中间时也能拼回完整报文', async () => {
    const body = toSse([{ type: 'keywords', keywords: ['收入', '经营单元'] }, DONE_EVENT])
    const cut = 30
    stubFetch(streamResponse([body.slice(0, cut), body.slice(cut)]))

    const onEvent = vi.fn()
    const onDone = vi.fn()
    streamQuery('q', null, { onEvent, onDone })

    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent.mock.calls[0][0]).toMatchObject({ keywords: ['收入', '经营单元'] })
  })

  it('忽略心跳、注释与非法 JSON，不中断整条流', async () => {
    const raw =
      ': keep-alive\n\n' + // SSE 注释（心跳）
      'data: not-json\n\n' + // 非法 JSON
      'data: \n\n' + // 空 data
      toSse([DONE_EVENT])

    stubFetch(streamResponse([raw]))

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()
    streamQuery('q', null, { onEvent, onDone, onError })

    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('error 事件走 onError 并把消息透出去', async () => {
    stubFetch(
      streamResponse([
        toSse([{ type: 'error', stage: 'guard', message: 'SQL 未通过安全校验' }]),
      ]),
    )

    const onError = vi.fn()
    streamQuery('q', null, { onError })
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('SQL 未通过安全校验'))
  })

  it('HTTP 非 2xx 时提示状态码', async () => {
    stubFetch(streamResponse([''], 500))

    const onError = vi.fn()
    streamQuery('q', null, { onError })
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('请求失败（HTTP 500）'))
  })

  it('响应没有 body 时也给出错误而不是静默', async () => {
    stubFetch({ ok: true, status: 200, body: null } as unknown as Response)

    const onError = vi.fn()
    streamQuery('q', null, { onError })
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('请求失败（HTTP 200）'))
  })

  it('网络异常转成可读提示', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Failed to fetch')))

    const onError = vi.fn()
    streamQuery('q', null, { onError })
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('Failed to fetch'))
  })

  it('主动取消不报错（AbortError 被吞掉）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(Object.assign(new Error('aborted'), { name: 'AbortError' })),
    )

    const onError = vi.fn()
    const cancel = streamQuery('q', null, { onError })
    cancel()

    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(onError).not.toHaveBeenCalled()
  })
})
