import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只替换 http，保留真实的 qs（它就是被这些断言覆盖的对象之一）
vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>()
  return {
    ...actual,
    http: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
  }
})

import { http } from './client'
import { chatApi, configApi, feedbackApi, logApi, modelApi, sessionApi, systemApi } from './endpoints'

const mockHttp = vi.mocked(http)

beforeEach(() => {
  mockHttp.get.mockResolvedValue({})
  mockHttp.post.mockResolvedValue({})
  mockHttp.put.mockResolvedValue({})
  mockHttp.patch.mockResolvedValue({})
  mockHttp.delete.mockResolvedValue({})
})

describe('chatApi', () => {
  it('把 session_id 缺失归一成 null，而不是 undefined', async () => {
    await chatApi.query('收入情况')
    expect(mockHttp.post).toHaveBeenCalledWith('/api/chat/query', {
      question: '收入情况',
      session_id: null,
    })
  })

  it('透传已有会话', async () => {
    await chatApi.query('收入情况', 9)
    expect(mockHttp.post).toHaveBeenCalledWith('/api/chat/query', {
      question: '收入情况',
      session_id: 9,
    })
  })
})

describe('sessionApi', () => {
  it('默认查 30 天且不带关键词', async () => {
    await sessionApi.list()
    expect(mockHttp.get).toHaveBeenCalledWith('/api/sessions?days=30')
  })

  it('关键词会参与查询串', async () => {
    await sessionApi.list(7, '收入')
    expect(mockHttp.get).toHaveBeenCalledWith('/api/sessions?days=7&keyword=%E6%94%B6%E5%85%A5')
  })

  it('会话相关接口路径正确', async () => {
    await sessionApi.detail(3)
    await sessionApi.rename(3, '新标题')
    await sessionApi.togglePin(3)
    await sessionApi.remove(3)
    await sessionApi.clearMessages(3)

    expect(mockHttp.get).toHaveBeenCalledWith('/api/sessions/3')
    expect(mockHttp.put).toHaveBeenCalledWith('/api/sessions/3/title', { title: '新标题' })
    expect(mockHttp.post).toHaveBeenCalledWith('/api/sessions/3/pin')
    expect(mockHttp.delete).toHaveBeenCalledWith('/api/sessions/3')
    expect(mockHttp.delete).toHaveBeenCalledWith('/api/sessions/3/messages')
  })

  it('新建会话带上默认标题与用户名', async () => {
    await sessionApi.create()
    expect(mockHttp.post).toHaveBeenCalledWith('/api/sessions', {
      title: '新对话',
      user_name: '管理员',
    })
  })

  it('收藏 / 取消收藏用查询参数传问题原文（空格编码成 +）', async () => {
    await sessionApi.toggleFavorite('2026 年各经营单元的收入')
    expect(mockHttp.post).toHaveBeenCalledWith(
      '/api/sessions/favorites?question=2026+%E5%B9%B4%E5%90%84%E7%BB%8F%E8%90%A5%E5%8D%95%E5%85%83%E7%9A%84%E6%94%B6%E5%85%A5',
    )
  })
})

describe('logApi', () => {
  it('日志列表带上全部过滤条件', async () => {
    await logApi.list(7, '收入', '管理员', 50)
    expect(mockHttp.get).toHaveBeenCalledWith(
      '/api/logs?days=7&keyword=%E6%94%B6%E5%85%A5&user_name=%E7%AE%A1%E7%90%86%E5%91%98&limit=50',
    )
  })

  it('汇总接口只带天数', async () => {
    await logApi.summary(90)
    expect(mockHttp.get).toHaveBeenCalledWith('/api/logs/summary?days=90')
  })
})

describe('feedbackApi', () => {
  it('列表默认值是 all / 第 1 页 / 10 条，空关键词被跳过', async () => {
    await feedbackApi.list({})
    expect(mockHttp.get).toHaveBeenCalledWith(
      '/api/feedback?status=all&page=1&page_size=10',
    )
  })

  it('显式传入的筛选项全部保留', async () => {
    await feedbackApi.list({ status: '待处理', keyword: '收入', userKeyword: '管理员', page: 2, pageSize: 20 })
    expect(mockHttp.get).toHaveBeenCalledWith(
      '/api/feedback?status=%E5%BE%85%E5%A4%84%E7%90%86&keyword=%E6%94%B6%E5%85%A5&user_keyword=%E7%AE%A1%E7%90%86%E5%91%98&page=2&page_size=20',
    )
  })

  it('提交反馈时把驼峰字段翻译成后端的下划线字段', async () => {
    await feedbackApi.create({ sessionId: 5, question: '收入情况', aiReply: 'AI 回复' })
    expect(mockHttp.post).toHaveBeenCalledWith('/api/feedback', {
      session_id: 5,
      question: '收入情况',
      message: '数据有误，实际数据与 AI 回复不一致',
      ai_reply: 'AI 回复',
      user_name: '管理员',
    })
  })

  it('更新状态时 remark 默认为空串', async () => {
    await feedbackApi.update(8, '已处理')
    expect(mockHttp.put).toHaveBeenCalledWith('/api/feedback/8', { status: '已处理', remark: '' })
  })
})

describe('configApi', () => {
  it('读取配置走 GET / PATCH', async () => {
    await configApi.getApp()
    await configApi.patchApp({ tts: false })
    await configApi.runtime()

    expect(mockHttp.get).toHaveBeenCalledWith('/api/config/app')
    expect(mockHttp.patch).toHaveBeenCalledWith('/api/config/app', { tts: false })
    expect(mockHttp.get).toHaveBeenCalledWith('/api/config/runtime')
  })
})

describe('modelApi', () => {
  it('新增模型时补齐可选字段，避免后端 422', async () => {
    await modelApi.add({ baseUrl: 'https://api.example.com', modelName: 'gpt-4o-mini' })
    expect(mockHttp.post).toHaveBeenCalledWith('/api/models', {
      base_url: 'https://api.example.com',
      model_name: 'gpt-4o-mini',
      api_key: '',
      name: '',
    })
  })

  it('选择与删除走路径 / 查询参数组合', async () => {
    await modelApi.select(2)
    await modelApi.remove(2)

    expect(mockHttp.post).toHaveBeenCalledWith('/api/models/select?model_id=2')
    expect(mockHttp.delete).toHaveBeenCalledWith('/api/models/2')
  })

  it('连通性测试允许字段为空（表示测当前选中模型）', async () => {
    await modelApi.test({})
    expect(mockHttp.post).toHaveBeenCalledWith('/api/models/test', {
      base_url: '',
      model_name: '',
      api_key: '',
    })
  })
})

describe('systemApi', () => {
  it('健康检查 / 管道 / 元数据路径正确', async () => {
    await systemApi.health()
    await systemApi.pipeline()
    await systemApi.metadata()

    expect(mockHttp.get).toHaveBeenCalledWith('/api/health')
    expect(mockHttp.get).toHaveBeenCalledWith('/api/pipeline')
    expect(mockHttp.get).toHaveBeenCalledWith('/api/metadata')
  })
})
