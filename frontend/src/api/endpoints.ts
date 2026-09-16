/** 按后端 router 分组的接口封装。页面只依赖这一层，不直接拼 URL。 */

import { http, qs } from './client'
import type {
  AppConfig,
  ChatSession,
  FeedbackItem,
  FeedbackPage,
  FeedbackStats,
  LogSummary,
  MetadataInfo,
  ModelItem,
  ModelTestResult,
  PipelineInfo,
  QueryLogItem,
  QueryPayload,
  QuickQuestions,
  SessionDetail,
} from '../types'

export const chatApi = {
  /** 同步问数：一次拿到完整结果（不含落库）。 */
  query: (question: string, sessionId?: number) =>
    http.post<QueryPayload>('/api/chat/query', { question, session_id: sessionId ?? null }),
}

export const sessionApi = {
  list: (days = 30, keyword = '') =>
    http.get<ChatSession[]>(`/api/sessions${qs({ days, keyword })}`),
  detail: (id: number) => http.get<SessionDetail>(`/api/sessions/${id}`),
  create: (title = '新对话', userName = '管理员') =>
    http.post<ChatSession>('/api/sessions', { title, user_name: userName }),
  rename: (id: number, title: string) =>
    http.put<SessionDetail>(`/api/sessions/${id}/title`, { title }),
  togglePin: (id: number) => http.post<{ pinned: boolean }>(`/api/sessions/${id}/pin`),
  remove: (id: number) => http.delete<{ deleted: boolean }>(`/api/sessions/${id}`),
  clearMessages: (id: number) =>
    http.delete<{ cleared: boolean }>(`/api/sessions/${id}/messages`),
  quickQuestions: () => http.get<QuickQuestions>('/api/sessions/quick-questions'),
  toggleFavorite: (question: string) =>
    http.post<{ favorites: string[] }>(`/api/sessions/favorites${qs({ question })}`),
}

export const logApi = {
  list: (days = 30, keyword = '', userName = '', limit = 100) =>
    http.get<QueryLogItem[]>(`/api/logs${qs({ days, keyword, user_name: userName, limit })}`),
  summary: (days = 30) => http.get<LogSummary>(`/api/logs/summary${qs({ days })}`),
}

export const feedbackApi = {
  list: (params: {
    status?: string
    keyword?: string
    userKeyword?: string
    page?: number
    pageSize?: number
  }) =>
    http.get<FeedbackPage>(
      `/api/feedback${qs({
        status: params.status ?? 'all',
        keyword: params.keyword ?? '',
        user_keyword: params.userKeyword ?? '',
        page: params.page ?? 1,
        page_size: params.pageSize ?? 10,
      })}`,
    ),
  stats: () => http.get<FeedbackStats>('/api/feedback/stats'),
  create: (payload: {
    sessionId: number
    question: string
    message?: string
    aiReply?: string
    userName?: string
  }) =>
    http.post<FeedbackItem>('/api/feedback', {
      session_id: payload.sessionId,
      question: payload.question,
      message: payload.message ?? '数据有误，实际数据与 AI 回复不一致',
      ai_reply: payload.aiReply ?? '',
      user_name: payload.userName ?? '管理员',
    }),
  update: (id: number, status: string, remark = '') =>
    http.put<FeedbackItem>(`/api/feedback/${id}`, { status, remark }),
}

export interface RuntimeConfig {
  model: {
    source: 'db_selected' | 'env'
    selected_id: number | null
    provider: string
    model_name: string
    base_url: string
    configured: boolean
    temperature: number
    use_llm: boolean
  }
  sql: { row_limit: number; timeout_seconds: number; max_correction_retry: number }
  recall: { top_k: number; max_tables: number }
}

export const configApi = {
  getApp: () => http.get<AppConfig>('/api/config/app'),
  patchApp: (patch: Partial<AppConfig>) => http.patch<AppConfig>('/api/config/app', patch),
  runtime: () => http.get<RuntimeConfig>('/api/config/runtime'),
}

export const modelApi = {
  list: () => http.get<ModelItem[]>('/api/models'),
  select: (modelId: number) => http.post<ModelItem>(`/api/models/select${qs({ model_id: modelId })}`),
  add: (payload: { baseUrl: string; modelName: string; apiKey?: string; name?: string }) =>
    http.post<ModelItem>('/api/models', {
      base_url: payload.baseUrl,
      model_name: payload.modelName,
      api_key: payload.apiKey ?? '',
      name: payload.name ?? '',
    }),
  remove: (id: number) => http.delete<{ deleted: boolean }>(`/api/models/${id}`),
  test: (payload: { baseUrl?: string; modelName?: string; apiKey?: string }) =>
    http.post<ModelTestResult>('/api/models/test', {
      base_url: payload.baseUrl ?? '',
      model_name: payload.modelName ?? '',
      api_key: payload.apiKey ?? '',
    }),
}

export const systemApi = {
  health: () =>
    http.get<{ status: string; app: string; llm_provider: string; llm_configured: boolean }>(
      '/api/health',
    ),
  pipeline: () => http.get<PipelineInfo>('/api/pipeline'),
  metadata: () => http.get<MetadataInfo>('/api/metadata'),
}
