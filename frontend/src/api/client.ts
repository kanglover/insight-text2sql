/**
 * 统一的 HTTP 客户端。
 *
 * 约定：后端所有接口都返回 `{code, message, data}`，`code === 0` 表示成功。
 * 这里把「解包 + 错误抛出」收敛到一处，页面里就不用重复判断了。
 */

import type { ApiResponse } from '../types'

/** 后端地址。默认走同源 `/api`，由 vite/nginx 反向代理。 */
const BASE_URL = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    // 后端校验失败（422）也会走到这里，尽量把可读信息透出去
    const text = await response.text().catch(() => '')
    throw new ApiError(extractDetail(text) || `请求失败（HTTP ${response.status}）`, response.status)
  }

  const body = (await response.json()) as ApiResponse<T>
  if (body.code !== 0) {
    throw new ApiError(body.message || '接口返回失败', response.status, body.code)
  }
  return body.data
}

/** FastAPI 的 422 结构是 `{detail: [{msg, loc}...]}`，转成人话。 */
function extractDetail(text: string): string {
  if (!text) return ''
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: string }
    if (typeof parsed.message === 'string') return parsed.message
    if (typeof parsed.detail === 'string') return parsed.detail
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => {
          const entry = item as { msg?: string; loc?: unknown[] }
          const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : ''
          return field ? `${String(field)}: ${entry.msg ?? ''}` : (entry.msg ?? '')
        })
        .join('；')
    }
  } catch {
    /* 不是 JSON，原样返回 */
  }
  return text.slice(0, 200)
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/** 把查询参数拼成 query string，自动跳过空值。 */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export { BASE_URL }
