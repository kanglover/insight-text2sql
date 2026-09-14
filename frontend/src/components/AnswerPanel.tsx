/**
 * AI 回复面板。
 *
 * 结构对齐 demo：
 *   分析过程（可折叠） → ① 数据发现 → ② 数据表格 → ③ 数据统计 → ④ 数据可视化
 *   → 结论 → 耗时/Token/生成方式 → 延伸问题
 */

import { useState } from 'react'
import type { QueryPayload } from '../types'
import { ChartView } from './ChartView'
import { DataTable, DotList, Module } from './DataTable'
import { Icon } from './Icon'
import { formatDuration, formatNumber } from '../utils/format'

interface AnswerPanelProps {
  payload: QueryPayload
  streaming?: boolean
  /** 正在流式输出时，展示实时进度步骤。 */
  liveSteps?: { label: string; status: string }[]
}

export function AnswerPanel({ payload, streaming, liveSteps }: AnswerPanelProps) {
  const [stepsOpen, setStepsOpen] = useState(false)
  const steps = liveSteps?.length ? liveSteps : payload.steps

  return (
    <div className="qa-ai">
      <div className="qa-ai-avatar">
        <Icon name="robot" size={17} />
      </div>
      <div className="qa-ai-body">
        {/* ---- 分析过程 ---- */}
        <div className="aa-summary-bar" onClick={() => setStepsOpen((open) => !open)}>
          <Icon name="microchip" size={14} />
          分析过程
          <span className={stepsOpen ? 'arrow open' : 'arrow'}>
            <Icon name="chevronRight" size={13} />
          </span>
          <span className="tail">
            {stepsOpen ? '点击收起' : `共 ${steps.length} 步，点击展开`}
          </span>
        </div>
        {stepsOpen ? (
          <div className="aa-steps">
            {steps.map((step, index) => (
              <div className={`aa-step ${step.status}`} key={`${step.label}-${index}`}>
                <span className="dot" />
                <span>{step.label}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--text-hint)', fontSize: 12 }}>
                  {labelOfStatus(step.status)}
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {streaming ? (
          <div className="mt-12 row muted" style={{ fontSize: 13 }}>
            <span className="spinner spinner-dark" />
            正在分析你的问题…
          </div>
        ) : null}

        {/* 出错时给出明确原因，而不是假装有结果 */}
        {payload.error ? (
          <div className="alert alert-error mt-12">
            <b>取数失败：</b>
            {payload.error}
          </div>
        ) : null}

        {!streaming || payload.row_count > 0 ? (
          <>
            {/* ---- ① 数据发现 ---- */}
            <Module index={1} title="数据发现">
              <DotList
                items={[
                  payload.keywords.length ? `识别关键词：${payload.keywords.join(' / ')}` : '',
                  payload.selected_tables.length
                    ? `命中数据表：${payload.selected_tables.join('、')}`
                    : '',
                  payload.metric_infos.length
                    ? `命中指标：${payload.metric_infos
                        .map((item) => item.metric_name ?? item.name ?? '')
                        .filter(Boolean)
                        .join('、')}`
                    : '',
                  payload.value_infos.length
                    ? `命中取值：${payload.value_infos
                        .slice(0, 6)
                        .map((item) => `${item.column_name ?? ''}「${item.value}」`)
                        .join('、')}`
                    : '',
                  payload.date_info && Object.keys(payload.date_info).length
                    ? `时间范围：${describeDate(payload.date_info)}`
                    : '',
                ]}
              />
              {payload.warnings.length ? (
                <div className="mt-8 muted" style={{ fontSize: 12.5 }}>
                  {payload.warnings.join('；')}
                </div>
              ) : null}
            </Module>

            {/* ---- ② 数据表格 ---- */}
            {payload.columns.length && payload.rows.length ? (
              <Module index={2} title={`数据表格（${payload.row_count} 行）`}>
                <div className="qa-ai-table-wrap">
                  <DataTable columns={payload.columns} rows={payload.rows} maxRows={200} />
                </div>
              </Module>
            ) : null}

            {/* ---- ③ 数据统计 ---- */}
            {payload.stats?.measures?.length ? (
              <Module index={3} title="数据统计">
                {payload.stats.measures.map((measure) => (
                  <DotList
                    key={measure.name}
                    items={[
                      `${measure.name}：合计 ${formatNumber(measure.sum)}，平均 ${formatNumber(
                        measure.avg,
                      )}`,
                      `最大值 ${formatNumber(measure.max)}，最小值 ${formatNumber(
                        measure.min,
                      )}（共 ${measure.count} 条有效值）`,
                    ]}
                  />
                ))}
              </Module>
            ) : null}

            {/* ---- ④ 数据可视化 ---- */}
            {payload.chart ? (
              <Module index={4} title="数据可视化">
                {describeChart(payload.chart) ? (
                  <div className="muted mb-8" style={{ fontSize: 13 }}>
                    {describeChart(payload.chart)}
                  </div>
                ) : null}
                <div className="qa-chart-wrap">
                  <ChartView spec={payload.chart} />
                </div>
              </Module>
            ) : null}

            {/* ---- 结论 ---- */}
            {payload.answer ? (
              <div className="qa-ai-module">
                <div className="mod-title">
                  <Icon name="sparkle" size={14} />
                  分析结论
                </div>
                <div className="mod-body">
                  <div className="qa-answer">{payload.answer}</div>
                </div>
              </div>
            ) : null}
          </>
        ) : null}

        {/* ---- SQL（可展开，方便核对口径） ---- */}
        {payload.sql ? <SqlDisclosure sql={payload.sql} /> : null}

        {/* ---- 元信息 ---- */}
        <div className="qa-meta">
          <span>
            耗时 <b>{formatDuration(payload.duration_ms)}</b>
          </span>
          <span>
            生成方式 <b>{payload.provider || '-'}</b>
          </span>
          <span>
            Token <b>{formatNumber(payload.token_usage)}</b>
          </span>
          <span>
            返回 <b>{formatNumber(payload.row_count)}</b> 行
          </span>
          {payload.db_info?.dialect ? (
            <span>
              数据库 <b>{payload.db_info.dialect}</b>
            </span>
          ) : null}
        </div>

        {/* ---- 延伸问题 ---- */}
        {payload.followups?.length ? (
          <div className="qa-ai-module">
            <div className="mod-title">
              <Icon name="link" size={14} />
              延伸问题
            </div>
            <div className="mod-body">
              <div className="followups">
                {payload.followups.map((question) => (
                  <button
                    className="followup-btn"
                    key={question}
                    data-followup={question}
                    type="button"
                  >
                    <Icon name="chat" size={13} />
                    {question}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function SqlDisclosure({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="qa-ai-module">
      <div
        className="mod-title"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="table" size={14} />
        生成的 SQL
        <span className={open ? 'arrow open' : 'arrow'} style={{ marginLeft: 'auto' }}>
          <Icon name="chevronRight" size={13} />
        </span>
      </div>
      {open ? (
        <div className="mod-body">
          <pre className="sql-block">{sql}</pre>
        </div>
      ) : null}
    </div>
  )
}

function labelOfStatus(status: string): string {
  if (status === 'success') return '完成'
  if (status === 'running') return '进行中'
  if (status === 'failed') return '失败'
  return ''
}

/** 用一句话说明这张图在画什么，替代容易被轴标签挤掉的坐标轴名称。 */
function describeChart(chart: NonNullable<QueryPayload['chart']>): string {
  if (chart.type === 'metric') return '本次结果为一个汇总值，已用指标卡呈现。'
  if (chart.type === 'pie') {
    return `按占比分布展示「${chart.name}」（共 ${chart.data.length} 个分片）。`
  }
  const ratio = chart.series.filter((name) => /率|占比|比例/.test(name))
  const base = `横轴为「${chart.x}」，纵轴为「${chart.series.join('、')}」`
  return ratio.length
    ? `${base}；其中「${ratio.join('、')}」为比率，使用右侧百分比坐标轴。`
    : `${base}。`
}

function describeDate(dateInfo: Record<string, unknown>): string {
  const parts: string[] = []
  for (const key of ['year', 'month', 'quarter', 'start', 'end']) {
    const value = dateInfo[key]
    if (value === undefined || value === null || value === '') continue
    parts.push(`${key}=${String(value)}`)
  }
  return parts.length ? parts.join('，') : '未识别到显式时间范围'
}

/** 供页面在用户消息旁展示的紧凑指标（如「21 行 · 1.2s」）。 */
export function summarize(payload: QueryPayload): string {
  return `${formatNumber(payload.row_count)} 行 · ${formatDuration(payload.duration_ms)}`
}
