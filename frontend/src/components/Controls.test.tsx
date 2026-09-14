import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Pagination, SearchBox, Toggle } from './Controls'

describe('Toggle', () => {
  it('用 switch 语义暴露状态', () => {
    const { rerender } = render(<Toggle checked={false} label="文字转语音" />)
    const switchButton = screen.getByRole('switch', { name: '文字转语音' })
    expect(switchButton).toHaveAttribute('aria-checked', 'false')

    rerender(<Toggle checked label="文字转语音" />)
    expect(screen.getByRole('switch', { name: '文字转语音' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('checked 时带上 on 类名，供 CSS 渲染滑轨', () => {
    const { rerender } = render(<Toggle checked={false} />)
    expect(screen.getByRole('switch').className).toBe('toggle')

    rerender(<Toggle checked />)
    expect(screen.getByRole('switch').className).toBe('toggle on')
  })

  it('点击回传取反后的值', async () => {
    const onChange = vi.fn()
    render(<Toggle checked={false} onChange={onChange} />)

    await userEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('disabled 时不可点也不回调', async () => {
    const onChange = vi.fn()
    render(<Toggle checked={false} onChange={onChange} disabled />)

    const switchButton = screen.getByRole('switch')
    expect(switchButton).toBeDisabled()
    await userEvent.click(switchButton)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('无 label 时给一个默认可读名', () => {
    render(<Toggle checked={false} />)
    expect(screen.getByRole('switch', { name: '开关' })).toBeInTheDocument()
  })
})

describe('SearchBox', () => {
  it('默认占位符是「搜索」，并把它作为可读名', () => {
    render(<SearchBox value="" onChange={() => {}} />)
    expect(screen.getByRole('textbox', { name: '搜索' })).toHaveAttribute('placeholder', '搜索')
  })

  it('输入时把最新值回传', async () => {
    const onChange = vi.fn()
    render(<SearchBox value="" onChange={onChange} placeholder="搜索问题内容" />)

    await userEvent.type(screen.getByRole('textbox'), '收')
    expect(onChange).toHaveBeenCalledWith('收')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('值由父级控制，本地不留状态', () => {
    render(<SearchBox value="" onChange={() => {}} />)
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('外部传入的 value 由父级控制', () => {
    render(<SearchBox value="各经营单元" onChange={() => {}} />)
    expect(screen.getByRole('textbox')).toHaveValue('各经营单元')
  })
})

describe('Pagination', () => {
  it('展示总条数与当前页码', () => {
    render(<Pagination page={1} pageSize={10} total={25} onPageChange={() => {}} />)
    expect(screen.getByText(/共 25 条 · 第 1\/3 页/)).toBeInTheDocument()
  })

  it('没有数据时页码下限是 1，不是 0', () => {
    render(<Pagination page={1} pageSize={10} total={0} onPageChange={() => {}} />)
    expect(screen.getByText(/第 1\/1 页/)).toBeInTheDocument()
  })

  it('首尾页时对应按钮禁用', () => {
    const { rerender } = render(
      <Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />,
    )
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled()

    rerender(<Pagination page={3} pageSize={10} total={30} onPageChange={() => {}} />)
    expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
  })

  it('页码窗口最多 5 个，靠后时向前滑动', () => {
    const { rerender } = render(
      <Pagination page={1} pageSize={10} total={100} onPageChange={() => {}} />,
    )
    expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '5' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '6' })).toBeNull()

    rerender(<Pagination page={10} pageSize={10} total={100} onPageChange={() => {}} />)
    expect(screen.getByRole('button', { name: '6' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '5' })).toBeNull()
  })

  it('当前页按钮带 active 类', () => {
    render(<Pagination page={2} pageSize={10} total={100} onPageChange={() => {}} />)
    expect(screen.getByRole('button', { name: '2' }).className).toBe('active')
  })

  it('点击页码回传目标页', async () => {
    const onPageChange = vi.fn()
    render(<Pagination page={1} pageSize={10} total={100} onPageChange={onPageChange} />)

    await userEvent.click(screen.getByRole('button', { name: '3' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('上一页 / 下一页按 ±1 计算', async () => {
    const onPageChange = vi.fn()
    render(<Pagination page={2} pageSize={10} total={100} onPageChange={onPageChange} />)

    await userEvent.click(screen.getByRole('button', { name: '上一页' }))
    await userEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(onPageChange.mock.calls).toEqual([[1], [3]])
  })

  it('不传 onPageSizeChange 时不渲染每页条数下拉', () => {
    render(<Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />)
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('切换每页条数时回传数字而非字符串', () => {
    const onPageSizeChange = vi.fn()
    render(
      <Pagination
        page={1}
        pageSize={10}
        total={30}
        onPageChange={() => {}}
        onPageSizeChange={onPageSizeChange}
      />,
    )

    const select = screen.getByRole('combobox', { name: '每页条数' })
    expect(select).toHaveValue('10')
    fireEvent.change(select, { target: { value: '50' } })
    expect(onPageSizeChange).toHaveBeenCalledWith(50)
  })
})
