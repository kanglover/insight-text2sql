import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataTable, DotList, Module } from './DataTable'

describe('DataTable', () => {
  it('没有列定义时整体不渲染', () => {
    const { container } = render(<DataTable columns={[]} rows={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('渲染表头与数据行', () => {
    render(
      <DataTable
        columns={['经营单元', '收入额']}
        rows={[
          ['北京', 1200],
          ['上海', 980],
        ]}
      />,
    )

    expect(screen.getByRole('columnheader', { name: '经营单元' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(3) // 表头 + 2 行
    expect(screen.getByText('北京')).toBeInTheDocument()
  })

  it('数值列右对齐并加千分位，文本列不处理', () => {
    render(<DataTable columns={['名称', '金额']} rows={[['北京', 12345.6]]} />)

    const cells = screen.getAllByRole('cell')
    expect(cells[0].className).toBe('')
    expect(cells[0]).toHaveTextContent('北京')
    expect(cells[1].className).toBe('num')
    expect(cells[1]).toHaveTextContent('12,345.6')
  })

  it('null 单元格显示短横线，而不是空白或 "null"', () => {
    render(<DataTable columns={['名称', '备注']} rows={[['北京', null]]} />)

    const cells = screen.getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('-')
    expect(cells[1]).not.toHaveTextContent('null')
  })

  it('超过 maxRows 时截断并提示剩余行数', () => {
    const rows = Array.from({ length: 5 }, (_, index) => [`单元${index}`, index])
    render(<DataTable columns={['名称', '序号']} rows={rows} maxRows={2} />)

    expect(screen.getAllByRole('row')).toHaveLength(3) // 表头 + 2 行
    expect(screen.getByText(/另有 3 行未展示/)).toBeInTheDocument()
  })

  it('不传 maxRows 时全部展示且不提示', () => {
    const rows = Array.from({ length: 5 }, (_, index) => [`单元${index}`, index])
    render(<DataTable columns={['名称', '序号']} rows={rows} />)

    expect(screen.getAllByRole('row')).toHaveLength(6)
    expect(screen.queryByText(/未展示/)).toBeNull()
  })

  it('刚好等于 maxRows 时不算截断', () => {
    render(<DataTable columns={['名称']} rows={[['a'], ['b']]} maxRows={2} />)
    expect(screen.queryByText(/未展示/)).toBeNull()
  })

  it('className 挂在外层容器上（供滚动区样式复用）', () => {
    const { container } = render(<DataTable columns={['名称']} rows={[['a']]} className="compact" />)
    expect(container.querySelector('.table-wrap')?.classList.contains('compact')).toBe(true)
  })
})

describe('Module', () => {
  it('渲染编号与标题', () => {
    render(
      <Module index={3} title="数据统计">
        <span>内容</span>
      </Module>,
    )

    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('数据统计')).toBeInTheDocument()
    expect(screen.getByText('内容')).toBeInTheDocument()
  })
})

describe('DotList', () => {
  it('逐条渲染列表项', () => {
    render(<DotList items={['命中数据表：dw_fact_revenue', '识别关键词：收入']} />)

    const items = document.querySelectorAll('.dot-li')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('命中数据表：dw_fact_revenue')
  })

  it('过滤掉空值（可选信息缺失时不留下空行）', () => {
    render(<DotList items={['有值', '', null as unknown as string, undefined as unknown as string]} />)
    expect(document.querySelectorAll('.dot-li')).toHaveLength(1)
  })

  it('全部为空时不渲染任何节点', () => {
    const { container } = render(<DotList items={['', null as unknown as string]} />)
    expect(container.innerHTML).toBe('')
  })
})
