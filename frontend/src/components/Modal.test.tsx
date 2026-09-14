import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Modal } from './Modal'

describe('Modal', () => {
  it('open 为 false 时不渲染任何内容（含遮罩）', () => {
    const { container } = render(
      <Modal open={false} title="问数详情" onClose={() => {}}>
        正文
      </Modal>,
    )

    expect(container.querySelector('.modal-overlay')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByText('正文')).toBeNull()
  })

  it('打开后暴露 dialog 语义与标题、副标题', () => {
    render(
      <Modal open title="问数详情" subtitle="2026-09-11 10:00:00" onClose={() => {}}>
        正文
      </Modal>,
    )

    const dialog = screen.getByRole('dialog', { name: '问数详情' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('2026-09-11 10:00:00')).toBeInTheDocument()
    expect(screen.getByText('正文')).toBeInTheDocument()
  })

  it('wide 时加宽弹窗', () => {
    const { rerender } = render(
      <Modal open title="详情" onClose={() => {}}>
        正文
      </Modal>,
    )
    expect(screen.getByRole('dialog').className).toBe('modal')

    rerender(
      <Modal open wide title="详情" onClose={() => {}}>
        正文
      </Modal>,
    )
    expect(screen.getByRole('dialog').className).toBe('modal wide')
  })

  it('点关闭按钮回调 onClose', async () => {
    const onClose = vi.fn()
    render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    await userEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('点遮罩关闭', () => {
    const onClose = vi.fn()
    const { container } = render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    fireEvent.click(container.querySelector('.modal-overlay') as Element)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('点弹窗内部不关闭（事件冒泡被阻断）', async () => {
    const onClose = vi.fn()
    render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    await userEvent.click(screen.getByText('正文'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('Esc 关闭', () => {
    const onClose = vi.fn()
    render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('关闭状态下不监听 Esc', () => {
    const onClose = vi.fn()
    render(
      <Modal open={false} title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('其他按键不触发关闭', () => {
    const onClose = vi.fn()
    render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('卸载后移除键盘监听，不会残留回调', () => {
    const onClose = vi.fn()
    const { unmount } = render(
      <Modal open title="详情" onClose={onClose}>
        正文
      </Modal>,
    )

    unmount()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('footer 可选', () => {
    const { rerender } = render(
      <Modal open title="详情" onClose={() => {}}>
        正文
      </Modal>,
    )
    expect(document.querySelector('.modal-footer')).toBeNull()

    rerender(
      <Modal open title="详情" onClose={() => {}} footer={<button>确定</button>}>
        正文
      </Modal>,
    )
    expect(screen.getByRole('button', { name: '确定' })).toBeInTheDocument()
  })
})
