import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api/endpoints', () => ({
  logApi: { list: vi.fn(), summary: vi.fn() },
}))

import { logApi } from '../api/endpoints'
import { LogsPage } from './LogsPage'
import { makeLogItem, makeSummary } from '../test/fixtures'

const ITEMS = Array.from({ length: 12 }, (_, index) =>
  makeLogItem({
    id: index + 1,
    question: `问题${index + 1}`,
    status: index === 1 ? '失败' : '成功',
  }),
)

/** makeLogItem 的默认问题文案，详情弹窗的几个用例复用。 */
const DEFAULT_Q = '2026 年各经营单元的收入情况'

function renderPage(items = ITEMS, summary = makeSummary()) {
  vi.mocked(logApi.list).mockResolvedValue(items)
  vi.mocked(logApi.summary).mockResolvedValue(summary)
  return render(<LogsPage />)
}

describe('LogsPage — 概览', () => {
  it('五个统计卡展示后端汇总', async () => {
    renderPage()

    const stats = await screen.findAllByText(/总问数/)
    expect(stats.length).toBeGreaterThan(0)
    const row = document.querySelector('.stat-row') as HTMLElement
    expect(row).toHaveTextContent('总问数')
    expect(row).toHaveTextContent('12')
    expect(row).toHaveTextContent('91.7%')
    expect(row).toHaveTextContent('失败数')
    expect(row).toHaveTextContent('1.50s')
  })

  it('汇总缺失时用安全默认值，不显示 NaN', async () => {
    vi.mocked(logApi.list).mockResolvedValue([])
    vi.mocked(logApi.summary).mockResolvedValue({
      total: 0,
      failed: 0,
      success_rate: 100,
      avg_duration_ms: 0,
      avg_tokens: 0,
    })
    render(<LogsPage />)

    await waitFor(() => expect(logApi.summary).toHaveBeenCalled())
    expect(document.body.textContent).not.toContain('NaN')
  })
})

describe('LogsPage — 表格', () => {
  it('默认展示第一页 10 条', async () => {
    renderPage()

    expect(await screen.findByText('问题1')).toBeInTheDocument()
    expect(screen.getByText('问题10')).toBeInTheDocument()
    expect(screen.queryByText('问题11')).toBeNull()
  })

  it('成功 / 失败用不同标签样式区分', async () => {
    renderPage()
    await screen.findByText('问题1')

    expect(screen.getByText('失败')).toHaveClass('tag-danger')
    expect(screen.getAllByText('成功')[0]).toHaveClass('tag-success')
  })

  it('翻页展示剩余记录', async () => {
    renderPage()
    await screen.findByText('问题1')

    await userEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByText('问题11')).toBeInTheDocument()
    expect(screen.queryByText('问题1')).toBeNull()
  })

  it('切换每页条数后回到第 1 页', async () => {
    renderPage()
    await screen.findByText('问题1')

    await userEvent.click(screen.getByRole('button', { name: '下一页' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: '每页条数' }), '50')

    expect(screen.getByText('问题1')).toBeInTheDocument()
    expect(screen.getByText('问题12')).toBeInTheDocument()
  })

  it('没有日志时给出下一步动作而不是空白表格', async () => {
    renderPage([])

    expect(await screen.findByText('暂无日志，先去「智能问数」问两个问题')).toBeInTheDocument()
  })
})

describe('LogsPage — 筛选', () => {
  it('点时间范围重新拉数并带上天数', async () => {
    renderPage()
    await screen.findByText('问题1')

    await userEvent.click(screen.getByRole('button', { name: '近 7 天' }))
    await waitFor(() => expect(logApi.list).toHaveBeenCalledWith(7, '', '', 500))
  })

  it('关键词变化触发重新查询', async () => {
    renderPage()
    await screen.findByText('问题1')

    await userEvent.type(screen.getByRole('textbox'), '收')
    await waitFor(() => expect(logApi.list).toHaveBeenCalledWith(30, '收', '', 500))
  })

  it('用户下拉的选项来自当前结果集', async () => {
    renderPage([
      makeLogItem({ user_name: '张三', question: '张三问的问题' }),
      makeLogItem({ id: 2, user_name: '李四', question: '李四问的问题' }),
    ])
    await screen.findByText('张三问的问题')

    const select = screen.getByRole('combobox', { name: '按用户筛选' })
    expect(within(select).getByRole('option', { name: '全部用户' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: '张三' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: '李四' })).toBeInTheDocument()

    await userEvent.selectOptions(select, '张三')
    await waitFor(() => expect(logApi.list).toHaveBeenCalledWith(30, '', '张三', 500))
  })

  it('刷新按钮重新请求', async () => {
    renderPage()
    await screen.findByText('问题1')
    const calls = vi.mocked(logApi.list).mock.calls.length

    await userEvent.click(screen.getByRole('button', { name: /刷新/ }))
    await waitFor(() => expect(vi.mocked(logApi.list).mock.calls.length).toBeGreaterThan(calls))
  })
})

describe('LogsPage — 异常', () => {
  it('加载失败时显示后端返回的原因', async () => {
    vi.mocked(logApi.list).mockRejectedValue(new Error('请求超时'))
    vi.mocked(logApi.summary).mockResolvedValue(makeSummary())
    render(<LogsPage />)

    expect(await screen.findByText('请求超时')).toBeInTheDocument()
  })
})

describe('LogsPage — 详情弹窗', () => {
  it('点「查看详情」展示 SQL、命中表与指标', async () => {
    renderPage([
      makeLogItem({
        question: '各经营单元的收入情况',
        sql: 'SELECT org_name FROM dw_dim_org',
        tables_used: ['dw_fact_revenue', 'dw_dim_org'],
      }),
    ])
    await screen.findByText('各经营单元的收入情况')

    await userEvent.click(screen.getByRole('button', { name: '查看详情' }))

    const dialog = screen.getByRole('dialog', { name: '问数详情' })
    expect(within(dialog).getByText('SELECT org_name FROM dw_dim_org')).toBeInTheDocument()
    expect(within(dialog).getByText('dw_fact_revenue')).toBeInTheDocument()
    expect(within(dialog).getByText(/耗时：1.23s/)).toBeInTheDocument()
    expect(within(dialog).getByText(/返回：21 行/)).toBeInTheDocument()
  })

  it('失败的记录会在弹窗里说明错误原因', async () => {
    renderPage([makeLogItem({ status: '失败', error: 'attempt to write a readonly database' })])
    await screen.findByText(DEFAULT_Q)

    await userEvent.click(screen.getByRole('button', { name: '查看详情' }))
    expect(screen.getByText('attempt to write a readonly database')).toBeInTheDocument()
  })

  it('没有命中表 / SQL 时显示占位文案', async () => {
    renderPage([makeLogItem({ tables_used: [], sql: '' })])
    await screen.findByText(DEFAULT_Q)

    await userEvent.click(screen.getByRole('button', { name: '查看详情' }))
    expect(screen.getByText('无')).toBeInTheDocument()
    expect(screen.getByText('（无）')).toBeInTheDocument()
  })

  it('点关闭后弹窗消失', async () => {
    renderPage([makeLogItem()])
    await screen.findByText(DEFAULT_Q)

    await userEvent.click(screen.getByRole('button', { name: '查看详情' }))
    const dialog = screen.getByRole('dialog')
    // 弹窗里「关闭」有两个：右上角图标按钮（aria-label）与底部文字按钮，这里点底部的
    await userEvent.click(within(dialog).getByText('关闭'))

    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('LogsPage — CSV 导出', () => {
  it('导出带 BOM 的 CSV，文件名含时间范围', async () => {
    const anchors: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      anchors.push(this)
    })
    const createObjectURL = vi.spyOn(URL, 'createObjectURL')

    renderPage([makeLogItem({ question: '各经营单元的收入情况' })])
    await screen.findByText('各经营单元的收入情况')

    await userEvent.click(screen.getByRole('button', { name: /导出 CSV/ }))

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(anchors).toHaveLength(1)
    expect(anchors[0].download).toBe('问数日志_近30天.csv')
    expect(anchors[0].href).toContain('blob:')
  })

  it('没有数据时导出按钮禁用', async () => {
    renderPage([])
    await screen.findByText(/暂无日志/)

    expect(screen.getByRole('button', { name: /导出 CSV/ })).toBeDisabled()
  })
})
