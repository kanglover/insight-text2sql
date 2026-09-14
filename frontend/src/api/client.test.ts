import { describe, expect, it, vi } from 'vitest'
import { ApiError, http, qs } from './client'

/** 构造一个最小可用的 fetch Response。 */
function response(body: unknown, init: { status?: number; raw?: string } = {}) {
  const status = init.status ?? 200
  const text = init.raw ?? JSON.stringify(body)
  return {
    ok: status < 400,
    status,
    json: async () => JSON.parse(text),
    text: async () => text,
  } as unknown as Response
}

function stubFetch(result: unknown) {
  const fn = vi.fn().mockResolvedValue(result)
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('http', () => {
  it('GET 解包 data 字段', async () => {
    const fetchMock = stubFetch(response({ code: 0, message: 'ok', data: { total: 3 } }))

    await expect(http.get<{ total: number }>('/api/logs')).resolves.toEqual({ total: 3 })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/logs')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('POST 带上 JSON body 与 method', async () => {
    const fetchMock = stubFetch(response({ code: 0, message: 'ok', data: null }))

    await http.post('/api/chat/query', { question: '收入情况' })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ question: '收入情况' }))
  })

  it('不传 body 时补空对象，避免后端解析失败', async () => {
    const fetchMock = stubFetch(response({ code: 0, message: 'ok', data: null }))

    await http.post('/api/sessions')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBe('{}')
  })

  it('各动词方法名正确', async () => {
    const fetchMock = stubFetch(response({ code: 0, message: 'ok', data: null }))

    await http.put('/api/a', {})
    await http.patch('/api/b', {})
    await http.delete('/api/c')

    expect(fetchMock.mock.calls.map((call) => (call[1] as RequestInit).method)).toEqual([
      'PUT',
      'PATCH',
      'DELETE',
    ])
  })

  it('HTTP 错误优先透出 FastAPI 的 422 明细', async () => {
    stubFetch(
      response(null, {
        status: 422,
        raw: JSON.stringify({
          detail: [
            { loc: ['body', 'question'], msg: 'field required' },
            { loc: ['body', 'session_id'], msg: 'not a valid integer' },
          ],
        }),
      }),
    )

    const error = await http.post('/api/chat/query', {}).catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(422)
    expect((error as ApiError).message).toBe('question: field required；session_id: not a valid integer')
  })

  it('detail 是字符串时直接用', async () => {
    stubFetch(response(null, { status: 400, raw: JSON.stringify({ detail: '问题不能为空' }) }))

    await expect(http.get('/api/x')).rejects.toThrow('问题不能为空')
  })

  it('message 字段优先级高于 detail', async () => {
    stubFetch(
      response(null, {
        status: 400,
        raw: JSON.stringify({ message: '业务失败', detail: '技术细节' }),
      }),
    )

    await expect(http.get('/api/x')).rejects.toThrow('业务失败')
  })

  it('非 JSON 响应体截断到 200 字符', async () => {
    stubFetch(response(null, { status: 502, raw: 'x'.repeat(500) }))

    const error = (await http.get('/api/x').catch((err: unknown) => err)) as ApiError
    expect(error.message).toHaveLength(200)
  })

  it('响应体为空时用状态码兜底', async () => {
    stubFetch(response(null, { status: 500, raw: '' }))

    await expect(http.get('/api/x')).rejects.toThrow('请求失败（HTTP 500）')
  })

  it('HTTP 200 但 code 非 0 也视为失败，并带上业务码', async () => {
    stubFetch(response({ code: 4001, message: 'SQL 被安全网关拦截', data: null }))

    const error = (await http.get('/api/x').catch((err: unknown) => err)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(4001)
    expect(error.message).toBe('SQL 被安全网关拦截')
  })

  it('code 非 0 且无 message 时给默认文案', async () => {
    stubFetch(response({ code: 5000, message: '', data: null }))

    await expect(http.get('/api/x')).rejects.toThrow('接口返回失败')
  })
})

describe('qs', () => {
  it('拼出查询串', () => {
    expect(qs({ days: 30, keyword: '收入' })).toBe('?days=30&keyword=%E6%94%B6%E5%85%A5')
  })

  it('跳过 undefined / null / 空串', () => {
    expect(qs({ a: undefined, b: null, c: '', d: 1 })).toBe('?d=1')
  })

  it('保留 0 与 false（它们是有意义的取值）', () => {
    expect(qs({ page: 0, pinned: false })).toBe('?page=0&pinned=false')
  })

  it('全是空值时返回空串，不留下孤立的问号', () => {
    expect(qs({ a: '', b: undefined })).toBe('')
  })
})
