/**
 * 测试夹具。
 *
 * 后端返回的结构字段多、嵌套深，用例里逐个手写会淹没断言本身。
 * 这里给几个工厂函数，用例只覆盖自己关心的字段。
 */

import type {
  AppConfig,
  ChatSession,
  LogSummary,
  QueryLogItem,
  QueryPayload,
  StreamEvent,
} from '../types'

export function makePayload(overrides: Partial<QueryPayload> = {}): QueryPayload {
  return {
    question: '2026 年各经营单元的收入情况',
    steps: [
      { label: '问题解析', node: 'parse', status: 'success' },
      { label: '元数据召回', node: 'recall', status: 'success' },
      { label: 'SQL 生成', node: 'generate', status: 'success' },
    ],
    duration_ms: 1234,
    sql: 'SELECT org_name, SUM(revenue) FROM dw_fact_revenue GROUP BY org_name',
    provider: 'rule',
    generation: { provider: 'rule', confidence: 0.9, intent: 'revenue_by_org' },
    selected_tables: ['dw_fact_revenue', 'dw_dim_org'],
    metric_infos: [{ metric_name: '收入额' }],
    value_infos: [{ column_name: 'org_name', value: '北京' }],
    keywords: ['收入', '经营单元'],
    date_info: { year: 2026 },
    db_info: { dialect: 'sqlite', version: '3.45' },
    examples: [],
    chart: {
      type: 'bar',
      x: 'org_name',
      series: ['收入额', '完成率'],
      data: [
        { name: '北京', 收入额: 1200, 完成率: 78.1 },
        { name: '上海', 收入额: 980, 完成率: 65.2 },
      ],
    },
    stats: {
      row_count: 2,
      measures: [{ name: '收入额', sum: 2180, avg: 1090, max: 1200, min: 980, count: 2 }],
    },
    answer: '2026 年收入最高的经营单元是北京。',
    followups: ['各行业的收入分布', '2025 年同期对比'],
    columns: ['org_name', '收入额'],
    rows: [
      ['北京', 1200],
      ['上海', 980],
    ],
    row_count: 2,
    error: null,
    warnings: [],
    token_usage: 512,
    ...overrides,
  }
}

export function makeLogItem(overrides: Partial<QueryLogItem> = {}): QueryLogItem {
  return {
    id: 1,
    session_id: 1,
    session_title: '新对话',
    user_name: '管理员',
    question: '2026 年各经营单元的收入情况',
    sql: 'SELECT 1',
    provider: 'rule',
    status: '成功',
    duration_ms: 1234,
    total_tokens: 512,
    row_count: 21,
    tables_used: ['dw_fact_revenue'],
    error: '',
    created_at: '2026-09-11 10:00:00',
    ...overrides,
  }
}

export function makeSummary(overrides: Partial<LogSummary> = {}): LogSummary {
  return { total: 12, failed: 1, success_rate: 91.7, avg_duration_ms: 1500, avg_tokens: 480, ...overrides }
}

export function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: 1,
    title: '新对话',
    user_name: '管理员',
    pinned: false,
    msg_count: 0,
    user_feedback: '',
    admin_feedback: '',
    created_at: '2026-09-11 10:00:00',
    updated_at: '2026-09-11 10:00:00',
    ...overrides,
  }
}

export function makeAppConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    greeting: true,
    suggestions: true,
    tts: true,
    stt: true,
    hotRecommend: true,
    modelConfig: true,
    greetingText: '你好，我是经管之星',
    greetingQuestions: ['各经营单元的收入情况', '各行业的收入分布'],
    hotThreshold: 3,
    favorites: ['各经营单元的收入情况'],
    maxGreetingQuestions: 10,
    ...overrides,
  }
}

/** 把 SSE 事件序列拼成服务端会吐出的报文（`data: {...}\n\n`）。 */
export function toSse(events: StreamEvent[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}
