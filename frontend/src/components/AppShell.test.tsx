import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../api/endpoints', () => ({
  systemApi: { health: vi.fn() },
}))

import { systemApi } from '../api/endpoints'
import { AppShell } from './AppShell'

const HEALTH = {
  status: 'ok',
  app: 'insight-text2sql',
  llm_provider: 'openai',
  llm_configured: true,
}

/** AppShell 挂载时会探活后端，所以每个用例都先把探活结果安排上。 */
function renderShell(path = '/') {
  vi.mocked(systemApi.health).mockResolvedValue(HEALTH)
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<AppShell />} />
      </Routes>
    </MemoryRouter>,
  )
}

function sidebar() {
  return document.querySelector('.sidebar') as HTMLElement
}

describe('AppShell — 基础结构', () => {
  it('顶栏展示品牌与副标题', () => {
    renderShell()

    expect(screen.getByText('经管之星')).toBeInTheDocument()
    expect(screen.getByText('智能问数 · Text2SQL')).toBeInTheDocument()
  })

  it('一级菜单齐全', () => {
    renderShell()

    expect(screen.getByRole('link', { name: '智能问数' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '系统管理' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '日志' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '反馈管理' })).toBeInTheDocument()
  })

  it('顶栏工具按钮可访问', () => {
    renderShell()

    expect(screen.getByRole('button', { name: '消息' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '帮助' })).toBeInTheDocument()
  })
})

describe('AppShell — 父子菜单', () => {
  it('默认展开系统管理与反馈管理', () => {
    renderShell()

    const groups = document.querySelectorAll('.sub-menu')
    expect(groups[0].classList.contains('open')).toBe(true)
    expect(groups[1].classList.contains('open')).toBe(true)
    expect(screen.getByRole('link', { name: '应用配置' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '回复校对' })).toBeInTheDocument()
  })

  it('点击父级可收起再展开', async () => {
    renderShell()

    await userEvent.click(screen.getByRole('button', { name: '系统管理' }))
    expect(document.querySelectorAll('.sub-menu')[0].classList.contains('open')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: '系统管理' }))
    expect(document.querySelectorAll('.sub-menu')[0].classList.contains('open')).toBe(true)
  })

  it('进入子页面时父级用 parent-active 提示层级，实心选中留给子项', () => {
    renderShell('/system/app')

    const parent = screen.getByRole('button', { name: '系统管理' })
    const child = screen.getByRole('link', { name: '应用配置' })

    expect(parent.className).toBe('menu-item parent-active')
    // 父子同时实心蓝会让层级看起来是平的，所以父级不能带 active
    expect(parent.className).not.toContain('menu-item active')
    expect(child.className).toBe('menu-item active')
  })

  it('切到另一个子页面时高亮跟着走', () => {
    renderShell('/system/model')

    expect(screen.getByRole('link', { name: '模型配置' }).className).toBe('menu-item active')
    expect(screen.getByRole('link', { name: '应用配置' }).className).toBe('menu-item')
  })
})

describe('AppShell — 一级菜单高亮', () => {
  it('首页高亮「智能问数」', () => {
    renderShell('/')
    expect(screen.getByRole('link', { name: '智能问数' }).className).toBe('menu-item active')
  })

  it('日志页高亮「日志」且首页不再高亮', () => {
    renderShell('/logs')

    expect(screen.getByRole('link', { name: '日志' }).className).toBe('menu-item active')
    expect(screen.getByRole('link', { name: '智能问数' }).className).toBe('menu-item')
  })

  it('不在任何菜单下的路径不高亮父级', () => {
    renderShell('/logs')
    expect(screen.getByRole('button', { name: '系统管理' }).className).toBe('menu-item')
  })
})

describe('AppShell — 账号菜单', () => {
  it('默认收起，点击后展示账号与后端模型状态', async () => {
    renderShell()

    expect(screen.queryByText('本地演示账号')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: '账号菜单' }))
    expect(screen.getByText('管理员')).toBeInTheDocument()
    expect(screen.getByText('本地演示账号')).toBeInTheDocument()
    expect(await screen.findByText('openai · 已配置密钥')).toBeInTheDocument()
  })

  it('密钥未配置时提示会走规则引擎（避免误以为是前端问题）', async () => {
    vi.mocked(systemApi.health).mockResolvedValue({ ...HEALTH, llm_configured: false })
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: '账号菜单' }))
    expect(await screen.findByText('openai · 未配置密钥（将走规则引擎）')).toBeInTheDocument()
  })

  it('后端探活失败时明确告知连不上', async () => {
    vi.mocked(systemApi.health).mockRejectedValue(new Error('ECONNREFUSED'))
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: '账号菜单' }))
    expect(await screen.findByText('无法连接后端')).toBeInTheDocument()
  })
})

describe('AppShell — 侧栏折叠', () => {
  it('点击收起后加 collapsed 类并隐藏文字', async () => {
    renderShell()
    expect(sidebar().classList.contains('collapsed')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: '折叠侧栏' }))
    expect(sidebar().classList.contains('collapsed')).toBe(true)
    expect(within(sidebar()).queryByText('收起')).toBeNull()
  })

  it('可再次展开', async () => {
    renderShell()

    await userEvent.click(screen.getByRole('button', { name: '折叠侧栏' }))
    await userEvent.click(screen.getByRole('button', { name: '折叠侧栏' }))
    expect(sidebar().classList.contains('collapsed')).toBe(false)
    expect(within(sidebar()).getByText('收起')).toBeInTheDocument()
  })
})
