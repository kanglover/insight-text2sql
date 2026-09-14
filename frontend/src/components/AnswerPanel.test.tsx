import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ChartView 依赖 canvas，这里只关心 AnswerPanel 有没有把图表模块接出来
vi.mock('./ChartView', () => ({
  ChartView: ({ spec }: { spec: { type: string } }) => (
    <div data-testid="chart" data-type={spec.type} />
  ),
}))

import { AnswerPanel, summarize } from './AnswerPanel'
import { makePayload } from '../test/fixtures'

function meta() {
  return document.querySelector('.qa-meta') as HTMLElement
}

describe('AnswerPanel — 分析过程', () => {
  it('默认折叠，只提示步数', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('分析过程')).toBeInTheDocument()
    expect(screen.getByText('共 3 步，点击展开')).toBeInTheDocument()
    expect(screen.queryByText('问题解析')).toBeNull()
  })

  it('展开后逐条列出步骤与状态', async () => {
    render(<AnswerPanel payload={makePayload()} />)

    await userEvent.click(screen.getByText('分析过程'))

    expect(screen.getByText('点击收起')).toBeInTheDocument()
    expect(screen.getByText('问题解析')).toBeInTheDocument()
    expect(screen.getByText('元数据召回')).toBeInTheDocument()
    expect(screen.getByText('SQL 生成')).toBeInTheDocument()
    expect(screen.getAllByText('完成')).toHaveLength(3)
  })

  it('再点一次收起', async () => {
    render(<AnswerPanel payload={makePayload()} />)

    await userEvent.click(screen.getByText('分析过程'))
    await userEvent.click(screen.getByText('分析过程'))
    expect(screen.queryByText('问题解析')).toBeNull()
  })

  it('状态文案覆盖成功 / 进行中 / 失败', async () => {
    render(
      <AnswerPanel
        payload={makePayload({
          steps: [
            { label: 'a', node: 'a', status: 'success' },
            { label: 'b', node: 'b', status: 'running' },
            { label: 'c', node: 'c', status: 'failed' },
          ],
        })}
      />,
    )

    await userEvent.click(screen.getByText('分析过程'))
    expect(screen.getByText('完成')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('流式进行中时优先展示实时步骤', async () => {
    render(
      <AnswerPanel
        payload={makePayload({ steps: [] })}
        streaming
        liveSteps={[{ label: '正在召回元数据', status: 'running' }]}
      />,
    )

    expect(screen.getByText('共 1 步，点击展开')).toBeInTheDocument()
    await userEvent.click(screen.getByText('分析过程'))
    expect(screen.getByText('正在召回元数据')).toBeInTheDocument()
  })

  it('流式进行中给出加载提示', () => {
    render(<AnswerPanel payload={makePayload({ row_count: 0 })} streaming />)
    expect(screen.getByText('正在分析你的问题…')).toBeInTheDocument()
  })
})

describe('AnswerPanel — 异常', () => {
  it('取数失败时明确说明原因', () => {
    render(
      <AnswerPanel
        payload={makePayload({ error: 'SQL 被安全网关拦截：禁止查询 sqlite_master' })}
      />,
    )

    expect(screen.getByText('取数失败：')).toBeInTheDocument()
    expect(screen.getByText(/禁止查询 sqlite_master/)).toBeInTheDocument()
  })

  it('流式且尚无结果时不渲染任何数据模块', () => {
    render(<AnswerPanel payload={makePayload({ row_count: 0, rows: [] })} streaming />)

    expect(screen.queryByText('数据发现')).toBeNull()
    expect(screen.queryByText('数据可视化')).toBeNull()
  })
})

describe('AnswerPanel — 四个模块', () => {
  it('① 数据发现汇总命中的关键词、表、指标、取值与时间', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('识别关键词：收入 / 经营单元')).toBeInTheDocument()
    expect(screen.getByText('命中数据表：dw_fact_revenue、dw_dim_org')).toBeInTheDocument()
    expect(screen.getByText('命中指标：收入额')).toBeInTheDocument()
    expect(screen.getByText('命中取值：org_name「北京」')).toBeInTheDocument()
    expect(screen.getByText('时间范围：year=2026')).toBeInTheDocument()
  })

  it('缺少的信息不占位（空行会被过滤掉）', () => {
    render(
      <AnswerPanel
        payload={makePayload({
          keywords: [],
          selected_tables: [],
          metric_infos: [],
          value_infos: [],
          date_info: {},
        })}
      />,
    )

    expect(screen.queryByText(/识别关键词/)).toBeNull()
    expect(screen.queryByText(/时间范围/)).toBeNull()
  })

  it('warnings 会一并展示', () => {
    render(<AnswerPanel payload={makePayload({ warnings: ['结果超过 200 行，仅展示前 200 行'] })} />)
    expect(screen.getByText('结果超过 200 行，仅展示前 200 行')).toBeInTheDocument()
  })

  it('② 数据表格标题带行数，且复用了 DataTable', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('数据表格（2 行）')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'org_name' })).toBeInTheDocument()
    expect(screen.getByText('北京')).toBeInTheDocument()
  })

  it('没有结果集时不渲染表格模块', () => {
    render(<AnswerPanel payload={makePayload({ columns: [], rows: [] })} />)
    expect(screen.queryByText(/数据表格/)).toBeNull()
  })

  it('③ 数据统计给出合计 / 平均 / 极值', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('数据统计')).toBeInTheDocument()
    expect(screen.getByText('收入额：合计 2,180，平均 1,090')).toBeInTheDocument()
    expect(screen.getByText('最大值 1,200，最小值 980（共 2 条有效值）')).toBeInTheDocument()
  })

  it('没有度量时不渲染统计模块', () => {
    render(<AnswerPanel payload={makePayload({ stats: { row_count: 0, measures: [] } })} />)
    expect(screen.queryByText('数据统计')).toBeNull()
  })

  it('④ 数据可视化把图表规格交给 ChartView，并用一句话说明画的是什么', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('数据可视化')).toBeInTheDocument()
    expect(screen.getByTestId('chart')).toHaveAttribute('data-type', 'bar')
    expect(
      screen.getByText(
        '横轴为「org_name」，纵轴为「收入额、完成率」；其中「完成率」为比率，使用右侧百分比坐标轴。',
      ),
    ).toBeInTheDocument()
  })

  it('指标卡的说明文案不同于坐标图', () => {
    render(
      <AnswerPanel
        payload={makePayload({ chart: { type: 'metric', metrics: [{ label: '总收入', value: 1 }] } })}
      />,
    )

    expect(screen.getByText('本次结果为一个汇总值，已用指标卡呈现。')).toBeInTheDocument()
  })

  it('饼图说明带分片数量', () => {
    render(
      <AnswerPanel
        payload={makePayload({
          chart: {
            type: 'pie',
            name: '行业占比',
            data: [
              { name: '制造业', value: 40 },
              { name: '金融业', value: 60 },
            ],
          },
        })}
      />,
    )

    expect(screen.getByText('按占比分布展示「行业占比」（共 2 个分片）。')).toBeInTheDocument()
  })

  it('没有 chart 时不渲染可视化模块', () => {
    render(<AnswerPanel payload={makePayload({ chart: null })} />)
    expect(screen.queryByText('数据可视化')).toBeNull()
  })

  it('结论、延伸问题各自成块', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.getByText('分析结论')).toBeInTheDocument()
    expect(screen.getByText('2026 年收入最高的经营单元是北京。')).toBeInTheDocument()
    expect(screen.getByText('延伸问题')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /各行业的收入分布/ })).toHaveAttribute(
      'data-followup',
      '各行业的收入分布',
    )
  })

  it('没有延伸问题时整个模块不出现', () => {
    render(<AnswerPanel payload={makePayload({ followups: [] })} />)
    expect(screen.queryByText('延伸问题')).toBeNull()
  })
})

describe('AnswerPanel — SQL 与元信息', () => {
  it('SQL 默认折叠，展开后可见全文', async () => {
    const sql = makePayload().sql
    render(<AnswerPanel payload={makePayload()} />)

    expect(screen.queryByText(new RegExp(sql.slice(0, 20)))).toBeNull()

    await userEvent.click(screen.getByText('生成的 SQL'))
    expect(screen.getByText(new RegExp(sql.slice(0, 20)))).toBeInTheDocument()
    expect(screen.getByText(sql)).toBeInTheDocument()
  })

  it('再点一次收回去', async () => {
    render(<AnswerPanel payload={makePayload()} />)

    await userEvent.click(screen.getByText('生成的 SQL'))
    await userEvent.click(screen.getByText('生成的 SQL'))
    expect(screen.queryByText(/SELECT org_name/)).toBeNull()
  })

  it('没有 SQL 时不渲染该区块', () => {
    render(<AnswerPanel payload={makePayload({ sql: '' })} />)
    expect(screen.queryByText('生成的 SQL')).toBeNull()
  })

  it('元信息展示耗时、生成方式、Token、行数与方言', () => {
    render(<AnswerPanel payload={makePayload()} />)

    expect(meta()).toHaveTextContent('耗时')
    expect(meta()).toHaveTextContent('1.23s')
    expect(meta()).toHaveTextContent('生成方式')
    expect(meta()).toHaveTextContent('rule')
    expect(meta()).toHaveTextContent('Token')
    expect(meta()).toHaveTextContent('512')
    expect(meta()).toHaveTextContent('返回')
    expect(meta()).toHaveTextContent('数据库')
    expect(meta()).toHaveTextContent('sqlite')
  })

  it('拿不到 provider / 方言时降级成短横线而不是 undefined', () => {
    render(<AnswerPanel payload={makePayload({ provider: '', db_info: {} })} />)

    expect(meta()).toHaveTextContent('生成方式')
    expect(meta()).not.toHaveTextContent('undefined')
    expect(meta()).not.toHaveTextContent('数据库')
  })
})

describe('summarize', () => {
  it('给出「行数 · 耗时」的紧凑摘要', () => {
    expect(summarize(makePayload())).toBe('2 行 · 1.23s')
  })
})
