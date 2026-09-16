/** 与后端 `app/schemas.py` 及各 router 返回结构一一对应。 */

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 一次问数里「分析过程」的一步。 */
export interface AnalysisStep {
  label: string
  node: string
  status: 'running' | 'success' | 'failed' | ''
}

/** 图表规格由后端推导，前端只负责渲染。 */
export type ChartSpec =
  | { type: 'metric'; metrics: { label: string; value: number | string }[] }
  | { type: 'pie'; name: string; data: { name: string; value: number }[] }
  | {
      type: 'bar' | 'line'
      x: string
      series: string[]
      data: Record<string, number | string>[]
    }

export interface MeasureStat {
  name: string
  sum: number
  avg: number
  max: number
  min: number
  count: number
}

export interface StatsSpec {
  row_count: number
  measures: MeasureStat[]
  tokens?: number
}

export interface MetricInfo {
  metric_name?: string
  name?: string
  formula?: string
  aliases?: string[]
  description?: string
  unit?: string
}

export interface ValueInfo {
  column_name?: string
  value: string
  synonyms?: string[]
}

export interface ExampleInfo {
  question: string
  sql?: string
  intent?: string
}

/** `/api/chat/*` 与 `done` 事件里的完整载荷。 */
export interface QueryPayload {
  question: string
  steps: AnalysisStep[]
  duration_ms: number
  sql: string
  provider: string
  generation: { provider?: string; confidence?: number; reason?: string; intent?: string }
  selected_tables: string[]
  metric_infos: MetricInfo[]
  value_infos: ValueInfo[]
  keywords: string[]
  date_info: Record<string, unknown>
  db_info: { dialect?: string; version?: string }
  examples: ExampleInfo[]
  chart: ChartSpec | null
  stats: StatsSpec
  answer: string
  followups: string[]
  columns: string[]
  rows: (number | string | null)[][]
  row_count: number
  error: string | null
  warnings: string[]
  token_usage: number
}

export interface ChatSession {
  id: number
  title: string
  user_name: string
  pinned: boolean
  msg_count: number
  user_feedback: string
  admin_feedback: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  payload: QueryPayload | Record<string, never>
  created_at: string
}

export interface SessionDetail extends ChatSession {
  messages: ChatMessage[]
}

export interface QuickQuestions {
  recent: string[]
  favorite: string[]
  recommend: string[]
}

export interface QueryLogItem {
  id: number
  session_id: number
  session_title: string
  user_name: string
  question: string
  sql: string
  provider: string
  status: '成功' | '失败' | string
  duration_ms: number
  total_tokens: number
  row_count: number
  tables_used: string[]
  error: string
  created_at: string
}

export interface LogSummary {
  total: number
  failed: number
  success_rate: number
  avg_duration_ms: number
  avg_tokens: number
}

export interface AppConfig {
  greeting: boolean
  suggestions: boolean
  tts: boolean
  stt: boolean
  hotRecommend: boolean
  modelConfig: boolean
  greetingText: string
  greetingQuestions: string[]
  hotThreshold: number
  favorites: string[]
  maxGreetingQuestions: number
}

export interface ModelItem {
  id: number
  name: string
  base_url: string
  model_name: string
  api_key_hint: string
  has_key: boolean
  selected: boolean
  reachable: boolean
  latency_ms: number
  note: string
}

export interface ModelTestResult {
  ok: boolean
  message: string
  latency_ms: number
  checked: 'remote' | 'local' | string
}

export interface FeedbackItem {
  id: number
  session_id: number
  question: string
  user_name: string
  message: string
  ai_reply: string
  status: '待处理' | '已处理' | string
  remark: string
  created_at: string
  updated_at: string
}

export interface FeedbackPage {
  items: FeedbackItem[]
  total: number
  page: number
  page_size: number
}

export interface FeedbackStats {
  total: number
  pending: number
  recent: number
}

export interface PipelineInfo {
  name: string
  entry: string
  nodes: { name: string; label: string }[]
  mermaid: string
}

export interface MetadataInfo {
  tables: {
    table_name: string
    comment: string
    role: string
    domain: string
    columns: { name: string; type: string; comment: string; role: string }[]
  }[]
  metrics: {
    name: string
    aliases: string[]
    formula: string
    unit: string
    description: string
  }[]
  examples: { question: string; sql: string; intent: string }[]
  value_count: number
}

/** SSE 事件（后端 `emit(...)` 的各种 type）。 */
export type StreamEvent =
  | { type: 'session'; session: ChatSession }
  | { type: 'progress'; step: string; node: string; status: string }
  | { type: 'keywords'; keywords: string[] }
  | { type: 'recall'; stage: string; count: number; items: { name: string; comment?: string; spec?: string; score: number }[] }
  | { type: 'tables'; selected: string[] }
  | { type: 'guard'; status: string; error: string }
  | { type: 'sql'; sql: string; tables: string[]; warnings: string[] }
  | { type: 'correction'; attempt: number; provider: string; reason: string; sql: string }
  | { type: 'result'; columns: string[]; rows: (number | string | null)[][]; row_count: number; duration_ms: number }
  | { type: 'chart'; chart: ChartSpec | null }
  | { type: 'stats'; stats: StatsSpec }
  | { type: 'answer'; answer: string; followups: string[] }
  | { type: 'error'; stage?: string; message: string }
  | { type: 'trace'; nodes: string[] }
  | { type: 'done'; message: QueryPayload; session_id: number }
