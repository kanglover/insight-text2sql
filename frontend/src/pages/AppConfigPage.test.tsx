import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api/endpoints', () => ({
  configApi: { getApp: vi.fn(), patchApp: vi.fn(), runtime: vi.fn() },
}))

import { configApi, type RuntimeConfig } from '../api/endpoints'
import { AppConfigPage } from './AppConfigPage'
import { makeAppConfig } from '../test/fixtures'

const RUNTIME: RuntimeConfig = {
  model: {
    source: 'env',
    selected_id: null,
    provider: 'openai',
    model_name: 'gpt-4o-mini',
    base_url: 'https://api.example.com',
    configured: true,
    temperature: 0,
    use_llm: true,
  },
  sql: { row_limit: 500, timeout_seconds: 30, max_correction_retry: 2 },
  recall: { top_k: 6, max_tables: 4 },
}

/** 后端 PATCH 是局部更新，返回整份配置；这里用夹具模拟同样的行为。 */
function renderPage(config = makeAppConfig()) {
  vi.mocked(configApi.getApp).mockResolvedValue(config)
  vi.mocked(configApi.runtime).mockResolvedValue(RUNTIME)
  vi.mocked(configApi.patchApp).mockImplementation(async (patch) => makeAppConfig(patch))
  return render(<AppConfigPage />)
}

function card(name: string) {
  return screen.getByText(name).closest('.app-card') as HTMLElement
}

describe('AppConfigPage — 能力开关', () => {
  it('六个开关各自渲染，状态来自后端', async () => {
    renderPage()

    for (const name of ['开场白', '延伸问题', '文字转语音', '语音转文字', '常问推荐', '模型配置']) {
      expect(await screen.findByRole('switch', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('switch', { name: '文字转语音' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('关闭时开关状态为 off', async () => {
    renderPage(makeAppConfig({ tts: false, stt: false }))

    expect(await screen.findByRole('switch', { name: '文字转语音' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(screen.getByRole('switch', { name: '语音转文字' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('每个开关都配了说明文案，避免只有名词看不懂', async () => {
    renderPage()

    expect(await screen.findByText('开启后，支持把 AI 回复转成语音播报')).toBeInTheDocument()
    expect(screen.getByText('开启后，支持用语音输入问题')).toBeInTheDocument()
  })

  it('切换开关时做局部 patch，不用整份配置覆盖', async () => {
    renderPage()
    const toggle = await screen.findByRole('switch', { name: '文字转语音' })

    await userEvent.click(toggle)

    expect(configApi.patchApp).toHaveBeenCalledWith({ tts: false })
    expect(screen.getByRole('switch', { name: '文字转语音' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('保存成功后给一条轻提示', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('switch', { name: '延伸问题' }))
    expect(await screen.findByText('配置已保存')).toBeInTheDocument()
  })

  it('保存失败时提示原因，并且不谎报成功', async () => {
    renderPage()
    vi.mocked(configApi.patchApp).mockRejectedValueOnce(new Error('后端未启动'))

    await userEvent.click(await screen.findByRole('switch', { name: '延伸问题' }))

    expect(await screen.findByText('后端未启动')).toBeInTheDocument()
    expect(screen.queryByText('配置已保存')).toBeNull()
  })
})

describe('AppConfigPage — 后端真实生效配置', () => {
  it('把环境变量里的模型与限制单独列出来', async () => {
    renderPage()
    await screen.findByText('后端真实生效配置')

    const panel = screen.getByText('后端真实生效配置').closest('.card') as HTMLElement
    expect(panel).toHaveTextContent('openai')
    expect(panel).toHaveTextContent('gpt-4o-mini')
    expect(panel).toHaveTextContent('已配置')
    expect(panel).toHaveTextContent('500')
    expect(panel).toHaveTextContent('30s')
    expect(panel).toHaveTextContent('6 / 4')
  })

  it('密钥未配置时直说', async () => {
    vi.mocked(configApi.getApp).mockResolvedValue(makeAppConfig())
    vi.mocked(configApi.runtime).mockResolvedValue({
      ...RUNTIME,
      model: { ...RUNTIME.model, configured: false },
    })
    render(<AppConfigPage />)

    const panel = (await screen.findByText('后端真实生效配置')).closest('.card') as HTMLElement
    expect(panel).toHaveTextContent('未配置')
  })
})

describe('AppConfigPage — 开场白设置', () => {
  it('打开弹窗时预填当前欢迎语与推荐问题', async () => {
    renderPage()
    await screen.findByRole('switch', { name: '开场白' })

    await userEvent.click(screen.getByRole('button', { name: '设置开场白' }))

    const dialog = screen.getByRole('dialog', { name: '开场白设置' })
    expect(within(dialog).getByLabelText('欢迎语')).toHaveValue('你好，我是经管之星')
    expect(within(dialog).getByLabelText('推荐问题')).toHaveValue(
      '各经营单元的收入情况\n各行业的收入分布',
    )
  })

  it('保存时去掉空行并 trim', async () => {
    renderPage()
    await screen.findByRole('switch', { name: '开场白' })
    await userEvent.click(screen.getByRole('button', { name: '设置开场白' }))

    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('推荐问题'), {
      target: { value: '  各经营单元的收入情况  \n\n\n各行业的收入分布\n   \n' },
    })
    fireEvent.change(within(dialog).getByLabelText('欢迎语'), {
      target: { value: '欢迎使用经管之星' },
    })

    await userEvent.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(configApi.patchApp).toHaveBeenCalledWith({
        greetingText: '欢迎使用经管之星',
        greetingQuestions: ['各经营单元的收入情况', '各行业的收入分布'],
      }),
    )
    expect(await screen.findByText('开场白已保存')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('推荐问题条数按后端上限截断', async () => {
    renderPage(makeAppConfig({ maxGreetingQuestions: 1 }))
    await screen.findByRole('switch', { name: '开场白' })
    await userEvent.click(screen.getByRole('button', { name: '设置开场白' }))

    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('推荐问题'), {
      target: { value: '第一条\n第二条\n第三条' },
    })
    await userEvent.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(configApi.patchApp).toHaveBeenCalledWith(
        expect.objectContaining({ greetingQuestions: ['第一条'] }),
      ),
    )
  })

  it('取消不会发起保存', async () => {
    renderPage()
    await screen.findByRole('switch', { name: '开场白' })
    await userEvent.click(screen.getByRole('button', { name: '设置开场白' }))

    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: '取消' }))

    expect(configApi.patchApp).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('AppConfigPage — 常问推荐设置', () => {
  it('展示当前收藏，并允许调整阈值', async () => {
    renderPage()
    await screen.findByRole('switch', { name: '常问推荐' })

    await userEvent.click(screen.getByRole('button', { name: '设置常问阈值' }))

    const dialog = screen.getByRole('dialog', { name: '常问推荐设置' })
    expect(within(dialog).getByText('各经营单元的收入情况')).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText('触发阈值（被问到的次数）'), {
      target: { value: '8' },
    })
    await userEvent.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() => expect(configApi.patchApp).toHaveBeenCalledWith({ hotThreshold: 8 }))
    expect(await screen.findByText('常问阈值已保存')).toBeInTheDocument()
  })

  it('没有收藏时给出提示而不是空白', async () => {
    renderPage(makeAppConfig({ favorites: [] }))
    await screen.findByRole('switch', { name: '常问推荐' })

    await userEvent.click(screen.getByRole('button', { name: '设置常问阈值' }))
    expect(screen.getByText('还没有收藏问题')).toBeInTheDocument()
  })
})

describe('AppConfigPage — 加载状态', () => {
  it('加载中显示占位', () => {
    vi.mocked(configApi.getApp).mockReturnValue(new Promise(() => {}))
    vi.mocked(configApi.runtime).mockResolvedValue(RUNTIME)
    render(<AppConfigPage />)

    expect(screen.getByText('加载中…')).toBeInTheDocument()
  })

  it('加载失败时显示错误而非永远转圈', async () => {
    vi.mocked(configApi.getApp).mockRejectedValue(new Error('配置读取失败'))
    vi.mocked(configApi.runtime).mockResolvedValue(RUNTIME)
    render(<AppConfigPage />)

    expect(await screen.findByText('配置读取失败')).toBeInTheDocument()
  })

  it('卡片区块保持可读的语义结构', async () => {
    renderPage()

    expect(await screen.findByText('应用能力开关')).toBeInTheDocument()
    expect(card('文字转语音')).toHaveTextContent('开启后，支持把 AI 回复转成语音播报')
  })
})
