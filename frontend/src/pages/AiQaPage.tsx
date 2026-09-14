/**
 * 智能问数页。
 *
 * 覆盖 demo 的完整交互：
 * - 左侧「近 30 天记录」：置顶 / 重命名 / 删除 / 新建；
 * - 欢迎态：开场白 + 推荐问题；
 * - 对话态：SSE 流式推送，分析过程逐步点亮；
 * - 回复区：分析过程 / 数据发现 / 表格 / 统计 / 图表 / 结论 / 耗时 Token / 延伸问题；
 * - 消息动作：复制、编辑、重新生成、收藏、语音播放、「数据有误」反馈；
 * - 输入区「常问 / 收藏 / 推荐」三 Tab 快捷面板，麦克风按钮语音输入。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { configApi, feedbackApi, sessionApi } from '../api/endpoints'
import { streamQuery } from '../api/stream'
import type {
  AppConfig,
  ChatMessage,
  ChatSession,
  QueryPayload,
  QuickQuestions,
  StreamEvent,
} from '../types'
import { AnswerPanel } from '../components/AnswerPanel'
import { Modal } from '../components/Modal'
import { Icon } from '../components/Icon'
import { useAsr, useTts } from '../hooks/useSpeech'
import { copyText, formatRelative, truncate } from '../utils/format'

const EMPTY_PAYLOAD: QueryPayload = {
  question: '',
  steps: [],
  duration_ms: 0,
  sql: '',
  provider: '',
  generation: {},
  selected_tables: [],
  metric_infos: [],
  value_infos: [],
  keywords: [],
  date_info: {},
  db_info: {},
  examples: [],
  chart: null,
  stats: { row_count: 0, measures: [] },
  answer: '',
  followups: [],
  columns: [],
  rows: [],
  row_count: 0,
  error: null,
  warnings: [],
  token_usage: 0,
}

interface Toast {
  text: string
  kind: 'info' | 'error' | 'success'
}

export function AiQaPage() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [quick, setQuick] = useState<QuickQuestions>({ recent: [], favorite: [], recommend: [] })
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [input, setInput] = useState('')
  /** 语音识别的中间结果（边说边出字），仅用于预览，不写进 input。 */
  const [voiceDraft, setVoiceDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [liveSteps, setLiveSteps] = useState<{ label: string; status: string }[]>([])
  const [livePayload, setLivePayload] = useState<QueryPayload | null>(null)
  const [toast, setToast] = useState<Toast | null>(null)
  const [qqOpen, setQqOpen] = useState(false)
  const [qqTab, setQqTab] = useState<'recent' | 'favorite' | 'recommend'>('recent')
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; session: ChatSession } | null>(
    null,
  )
  const [renameTarget, setRenameTarget] = useState<ChatSession | null>(null)
  const [renameText, setRenameText] = useState('')
  const [feedbackTarget, setFeedbackTarget] = useState<{
    question: string
    answer: string
  } | null>(null)
  const [feedbackText, setFeedbackText] = useState('数据有误，实际数据与 AI 回复不一致')

  const abortRef = useRef<(() => void) | null>(null)
  const chatRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const notify = useCallback((text: string, kind: Toast['kind'] = 'info') => {
    setToast({ text, kind })
    window.setTimeout(() => setToast(null), 2600)
  }, [])

  /* ------------------------------------------------------------ 语音能力 */

  // 播报：把 AI 回复念出来。是否展示按钮由「应用配置 → 文字转语音」决定。
  const tts = useTts()

  // 语音输入：识别结果追加到输入框，中间结果只做预览。
  const asr = useAsr({
    onFinal: (text) => {
      setInput((prev) => (prev ? `${prev}${text}` : text))
      setVoiceDraft('')
    },
    onInterim: (text) => setVoiceDraft(text),
    onError: (message) => {
      setVoiceDraft('')
      notify(message, 'error')
    },
  })

  /* ------------------------------------------------------------ 数据加载 */

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await sessionApi.list(30))
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }, [notify])

  const loadQuick = useCallback(async () => {
    try {
      setQuick(await sessionApi.quickQuestions())
    } catch {
      /* 快捷问题拿不到不影响主流程 */
    }
  }, [])

  useEffect(() => {
    void loadSessions()
    void loadQuick()
    configApi
      .getApp()
      .then(setConfig)
      .catch(() => setConfig(null))
  }, [loadSessions, loadQuick])

  useEffect(() => {
    if (activeId === null) {
      setMessages([])
      return
    }
    sessionApi
      .detail(activeId)
      .then((detail) => setMessages(detail.messages))
      .catch((error) => notify((error as Error).message, 'error'))
  }, [activeId, notify])

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, livePayload, liveSteps])

  /* ------------------------------------------------------------ 流式问数 */

  const ask = useCallback(
    (question: string) => {
      const text = question.trim()
      if (!text || streaming) return

      // 开始新提问时停掉正在念的旧回复，并把未定稿的语音草稿清掉
      tts.stop()
      setVoiceDraft('')
      setInput('')
      setQqOpen(false)
      setStreaming(true)
      setLiveSteps([])
      setLivePayload(null)

      // 立刻把用户消息渲染出来（乐观更新），不等后端回包
      setMessages((list) => [
        ...list,
        {
          id: -Date.now(),
          role: 'user',
          content: text,
          payload: {},
          created_at: new Date().toISOString(),
        },
      ])

      abortRef.current = streamQuery(text, activeId, {
        onEvent: (event: StreamEvent) => {
          if (event.type === 'progress') {
            setLiveSteps((steps) => mergeStep(steps, event.step, event.status))
            return
          }
          setLivePayload((payload) => applyEvent(payload ?? { ...EMPTY_PAYLOAD, question: text }, event))
        },
        onDone: (payload, sessionId) => {
          setStreaming(false)
          setLiveSteps([])
          setLivePayload(null)
          setActiveId(sessionId)
          setMessages((list) => [
            ...list.filter((item) => item.id >= 0 || item.content !== text),
            {
              id: Date.now(),
              role: 'assistant',
              content: payload.answer,
              payload,
              created_at: new Date().toISOString(),
            },
          ])
          void loadSessions()
          void loadQuick()
        },
        onError: (message) => {
          setStreaming(false)
          setLiveSteps([])
          setLivePayload(null)
          notify(message, 'error')
          setMessages((list) => [
            ...list,
            {
              id: Date.now(),
              role: 'assistant',
              content: `本次问数失败：${message}`,
              payload: { ...EMPTY_PAYLOAD, error: message },
              created_at: new Date().toISOString(),
            },
          ])
        },
      })
    },
    [activeId, streaming, notify, loadSessions, loadQuick],
  )

  useEffect(() => () => abortRef.current?.(), [])

  /* ------------------------------------------------------------ 会话操作 */

  const startNewChat = () => {
    abortRef.current?.()
    tts.stop()
    asr.stop()
    setStreaming(false)
    setActiveId(null)
    setMessages([])
    setLivePayload(null)
    setInput('')
    setVoiceDraft('')
    inputRef.current?.focus()
  }

  const handlePin = async (session: ChatSession) => {
    setCtxMenu(null)
    try {
      const result = await sessionApi.togglePin(session.id)
      notify(result.pinned ? '已置顶' : '已取消置顶', 'success')
      await loadSessions()
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }

  const handleDelete = async (session: ChatSession) => {
    setCtxMenu(null)
    try {
      await sessionApi.remove(session.id)
      notify('会话已删除', 'success')
      if (activeId === session.id) startNewChat()
      await loadSessions()
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }

  const submitRename = async () => {
    if (!renameTarget) return
    try {
      await sessionApi.rename(renameTarget.id, renameText.trim())
      notify('已重命名', 'success')
      setRenameTarget(null)
      await loadSessions()
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }

  const toggleFavorite = async (question: string) => {
    try {
      const result = await sessionApi.toggleFavorite(question)
      const added = result.favorites.includes(question)
      notify(added ? '已加入收藏' : '已取消收藏', 'success')
      await loadQuick()
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }

  const submitFeedback = async () => {
    if (!feedbackTarget) return
    try {
      await feedbackApi.create({
        sessionId: activeId ?? 0,
        question: feedbackTarget.question,
        message: feedbackText,
        aiReply: feedbackTarget.answer,
      })
      notify('已提交，管理员会在「回复校对」中处理', 'success')
      setFeedbackTarget(null)
      setFeedbackText('数据有误，实际数据与 AI 回复不一致')
    } catch (error) {
      notify((error as Error).message, 'error')
    }
  }

  /* ------------------------------------------------------------ 渲染 */

  const hasConversation = messages.length > 0 || streaming
  const greetingQuestions = useMemo(() => {
    const list = config?.greetingQuestions?.length
      ? config.greetingQuestions
      : quick.recommend
    return list.slice(0, 6)
  }, [config, quick.recommend])

  const qqItems =
    qqTab === 'recent' ? quick.recent : qqTab === 'favorite' ? quick.favorite : quick.recommend

  return (
    <div className="qa-layout" onClick={() => setCtxMenu(null)}>
      {/* ---------------- 会话侧栏 ---------------- */}
      {sidebarOpen ? (
        <aside className="qa-sidebar">
          <div className="qa-sb-top">
            <div className="qa-sb-logo">
              <span className="qa-sb-logo-icon">
                <Icon name="sparkle" size={15} />
              </span>
              <span className="qa-sb-brand">智能问数</span>
            </div>
            <button
              className="qa-sb-collapse"
              onClick={() => setSidebarOpen(false)}
              aria-label="收起会话列表"
            >
              <Icon name="chevronLeft" size={15} />
            </button>
          </div>

          <button className="qa-sb-newchat" onClick={startNewChat}>
            <Icon name="plus" size={15} />
            新建对话
          </button>

          <div className="qa-sb-group">近 30 天记录</div>
          <div className="qa-sb-list">
            {sessions.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px 8px' }}>
                暂无历史会话
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  className={`qa-sb-item${session.id === activeId ? ' active' : ''}${
                    session.pinned ? ' pinned' : ''
                  }`}
                  onClick={() => {
                    setActiveId(session.id)
                    setLivePayload(null)
                  }}
                >
                  {session.pinned ? (
                    <span className="pin-mark">
                      <Icon name="pin" size={12} />
                    </span>
                  ) : null}
                  <span className="title" title={session.title}>
                    {truncate(session.title, 14)}
                  </span>
                  <span className="muted" style={{ fontSize: 11 }}>
                    {formatRelative(session.updated_at).replace('前', '')}
                  </span>
                  <button
                    className="more"
                    onClick={(event) => {
                      event.stopPropagation()
                      const rect = (event.target as HTMLElement).getBoundingClientRect()
                      setCtxMenu({ x: rect.left - 120, y: rect.bottom + 4, session })
                    }}
                    aria-label="更多操作"
                  >
                    <Icon name="chevronDown" size={13} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>
      ) : (
        <button className="qa-sidebar-rail" onClick={() => setSidebarOpen(true)} aria-label="展开会话列表">
          <Icon name="panelLeft" size={16} />
          <Icon name="plus" size={16} />
        </button>
      )}

      {/* ---------------- 主区域 ---------------- */}
      <div className="qa-main">
        <div className="qa-topbar">
          <span className="qa-title">
            {activeId
              ? (sessions.find((item) => item.id === activeId)?.title ?? '对话')
              : '新对话'}
          </span>
          <span className="spacer" />
          {config?.modelConfig !== false ? (
            <span className="model-chip">
              {config?.hotRecommend ? '智能推荐已开启' : '智能推荐已关闭'}
            </span>
          ) : null}
          <button
            className="btn btn-ghost btn-sm"
            onClick={startNewChat}
            title="清空当前对话内容"
          >
            <Icon name="refresh" size={14} />
            新对话
          </button>
        </div>

        {hasConversation ? (
          <div className="qa-chat" ref={chatRef}>
            {messages.map((message) =>
              message.role === 'user' ? (
                <UserMessage
                  key={message.id}
                  content={message.content}
                  onEdit={() => {
                    setInput(message.content)
                    inputRef.current?.focus()
                  }}
                  onCopy={async () => {
                    notify((await copyText(message.content)) ? '已复制' : '复制失败', 'success')
                  }}
                />
              ) : (
                <div className="qa-msg" key={message.id}>
                  <AnswerPanel payload={message.payload as QueryPayload} />
                  <AssistantActions
                    showSpeak={config?.tts !== false}
                    speakSupported={tts.supported}
                    speaking={tts.speakingId === String(message.id)}
                    onSpeak={() => tts.speak(String(message.id), message.content)}
                    onFavorite={() => toggleFavorite(message.content)}
                    onRegenerate={() => ask(findLastQuestion(messages, message.id))}
                    onCopy={async () => {
                      const payload = message.payload as QueryPayload
                      const ok = await copyText(payload.sql || message.content)
                      notify(ok ? '已复制' : '复制失败', 'success')
                    }}
                    onFeedback={() =>
                      setFeedbackTarget({
                        question: findLastQuestion(messages, message.id),
                        answer: message.content,
                      })
                    }
                  />
                </div>
              ),
            )}

            {streaming ? (
              <div className="qa-msg">
                <AnswerPanel
                  payload={livePayload ?? { ...EMPTY_PAYLOAD, question: input }}
                  streaming
                  liveSteps={liveSteps}
                />
              </div>
            ) : null}
          </div>
        ) : (
          <div className="qa-welcome">
            <div className="qa-welcome-inner">
              <h1>经管之星 · 智能问数</h1>
              <h2>用一句话问出经营数据</h2>
              <p className="qa-desc">
                {config?.greeting !== false
                  ? config?.greetingText ||
                    '欢迎使用智能 AI 问数，您可以向我咨询经营数据、报表分析相关问题。'
                  : '直接输入你的问题即可。'}
              </p>

              {config?.suggestions !== false && greetingQuestions.length ? (
                <div className="qa-quick-section">
                  <div className="qa-quick-title">你可以这样问</div>
                  <div className="qa-quick-grid">
                    {chunk(greetingQuestions, 2).map((row, index) => (
                      <div className="qa-quick-row" key={index}>
                        {row.map((question) => (
                          <button
                            className="qa-quick-btn"
                            key={question}
                            onClick={() => ask(question)}
                          >
                            {question}
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* ---------------- 输入区 ---------------- */}
        <div className="qa-input-area">
          <div className="qa-input-inner">
            {qqOpen ? (
              <div className="qq-panel">
                <div className="qq-header">
                  <span>快捷提问</span>
                  <button className="modal-close" onClick={() => setQqOpen(false)} aria-label="关闭">
                    <Icon name="close" size={14} />
                  </button>
                </div>
                <div className="qq-tabs">
                  <button
                    className={qqTab === 'recent' ? 'qq-tab active' : 'qq-tab'}
                    onClick={() => setQqTab('recent')}
                  >
                    常问
                  </button>
                  <button
                    className={qqTab === 'favorite' ? 'qq-tab active' : 'qq-tab'}
                    onClick={() => setQqTab('favorite')}
                  >
                    收藏
                  </button>
                  <button
                    className={qqTab === 'recommend' ? 'qq-tab active' : 'qq-tab'}
                    onClick={() => setQqTab('recommend')}
                  >
                    推荐
                  </button>
                </div>
                <div className="qq-list">
                  {qqItems.length === 0 ? (
                    <div className="empty-state" style={{ padding: '20px 8px' }}>
                      暂无内容，先去问两个问题吧
                    </div>
                  ) : (
                    qqItems.map((question) => (
                      <button className="qq-item" key={question} onClick={() => ask(question)}>
                        <Icon name="chat" size={13} />
                        <span className="txt">{question}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            ) : null}

            <div className="qa-input-box">
              <button
                className={qqOpen ? 'input-icon-btn active' : 'input-icon-btn'}
                onClick={() => setQqOpen((value) => !value)}
                title="常问 / 收藏"
                aria-label="常问和收藏"
              >
                <Icon name="sparkle" size={16} />
              </button>
              <textarea
                ref={inputRef}
                rows={1}
                value={voiceDraft ? `${input}${voiceDraft}` : input}
                placeholder={
                  asr.listening ? '正在聆听，请说话…' : '输入你的问题，例如：2026 年各经营单元的收入和完成率'
                }
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    ask(input)
                  }
                }}
                disabled={streaming}
              />
              {config?.stt === true ? (
                <button
                  className={asr.listening ? 'input-icon-btn mic-on' : 'input-icon-btn'}
                  onClick={asr.toggle}
                  disabled={streaming || !asr.supported}
                  title={
                    asr.supported
                      ? asr.listening
                        ? '停止录音'
                        : '语音输入'
                      : '当前浏览器不支持语音输入（建议 Chrome / Edge）'
                  }
                  aria-label="语音输入"
                  aria-pressed={asr.listening}
                >
                  <Icon name={asr.listening ? 'stop' : 'microphone'} size={16} />
                </button>
              ) : null}
              <button
                className="send-btn"
                onClick={() => ask(input)}
                disabled={streaming || !(input.trim() || voiceDraft.trim())}
                aria-label="发送"
              >
                {streaming ? <span className="spinner" /> : <Icon name="send" size={16} />}
              </button>
            </div>
            <div className="qa-input-hint">
              <span>
                {asr.listening ? '正在识别语音，说完会自动填入输入框' : 'Enter 发送，Shift + Enter 换行'}
              </span>
              <span>问题越具体，取数越准</span>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- 会话右键菜单 ---------------- */}
      {ctxMenu ? (
        <div
          className="ctx-menu"
          style={{ left: Math.max(8, ctxMenu.x), top: ctxMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <button onClick={() => handlePin(ctxMenu.session)}>
            <Icon name="pin" size={13} />
            {ctxMenu.session.pinned ? '取消置顶' : '置顶'}
          </button>
          <button
            onClick={() => {
              setRenameText(ctxMenu.session.title)
              setRenameTarget(ctxMenu.session)
              setCtxMenu(null)
            }}
          >
            <Icon name="edit" size={13} />
            重命名
          </button>
          <button className="danger" onClick={() => handleDelete(ctxMenu.session)}>
            <Icon name="trash" size={13} />
            删除
          </button>
        </div>
      ) : null}

      {/* ---------------- 重命名弹窗 ---------------- */}
      <Modal
        open={Boolean(renameTarget)}
        title="重命名对话"
        onClose={() => setRenameTarget(null)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setRenameTarget(null)}>
              取消
            </button>
            <button className="btn btn-primary" onClick={submitRename} disabled={!renameText.trim()}>
              保存
            </button>
          </>
        }
      >
        <div className="field">
          <label htmlFor="rename-input">对话名称</label>
          <input
            id="rename-input"
            className="input"
            value={renameText}
            onChange={(event) => setRenameText(event.target.value)}
            maxLength={128}
          />
        </div>
      </Modal>

      {/* ---------------- 反馈弹窗 ---------------- */}
      <Modal
        open={Boolean(feedbackTarget)}
        title="反馈数据有误"
        subtitle="提交后会进入「反馈管理 → 回复校对」，由管理员核对口径"
        onClose={() => setFeedbackTarget(null)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setFeedbackTarget(null)}>
              取消
            </button>
            <button className="btn btn-primary" onClick={submitFeedback}>
              提交反馈
            </button>
          </>
        }
      >
        <div className="field">
          <label>原始问题</label>
          <div className="sql-block">{feedbackTarget?.question}</div>
        </div>
        <div className="field">
          <label htmlFor="feedback-text">问题描述</label>
          <textarea
            id="feedback-text"
            className="textarea"
            value={feedbackText}
            onChange={(event) => setFeedbackText(event.target.value)}
            maxLength={1000}
          />
        </div>
      </Modal>

      {toast ? <div className={`toast toast-${toast.kind}`}>{toast.text}</div> : null}
    </div>
  )
}

/* ------------------------------------------------------------------ 子组件 */

function UserMessage({
  content,
  onEdit,
  onCopy,
}: {
  content: string
  onEdit: () => void
  onCopy: () => void
}) {
  return (
    <div className="qa-msg qa-msg-user" style={{ flexDirection: 'column', alignItems: 'flex-end' }}>
      <div className="bubble">{content}</div>
      <div className="qa-msg-actions">
        <button onClick={onCopy}>
          <Icon name="copy" size={12} />
          复制
        </button>
        <button onClick={onEdit}>
          <Icon name="edit" size={12} />
          编辑
        </button>
      </div>
    </div>
  )
}

function AssistantActions({
  onFavorite,
  onRegenerate,
  onCopy,
  onFeedback,
  showSpeak,
  speakSupported,
  speaking,
  onSpeak,
}: {
  onFavorite: () => void
  onRegenerate: () => void
  onCopy: () => void
  onFeedback: () => void
  showSpeak: boolean
  speakSupported: boolean
  speaking: boolean
  onSpeak: () => void
}) {
  return (
    <div className="qa-msg-actions" style={{ justifyContent: 'flex-start', paddingLeft: 44 }}>
      <button onClick={onCopy}>
        <Icon name="copy" size={12} />
        复制
      </button>
      <button onClick={onFavorite}>
        <Icon name="star" size={12} />
        收藏
      </button>
      <button onClick={onRegenerate}>
        <Icon name="refresh" size={12} />
        重新生成
      </button>
      {showSpeak ? (
        <button
          className={speaking ? 'speaking' : undefined}
          onClick={onSpeak}
          disabled={!speakSupported}
          title={
            speakSupported
              ? speaking
                ? '停止播报'
                : '语音播放本条回复'
              : '当前浏览器不支持语音播报'
          }
        >
          <Icon name={speaking ? 'volumeOff' : 'volume'} size={12} />
          {speaking ? '停止播报' : '语音播放'}
        </button>
      ) : null}
      <button onClick={onFeedback}>
        <Icon name="alert" size={12} />
        数据有误
      </button>
    </div>
  )
}

/* ------------------------------------------------------------------ 工具函数 */

function mergeStep(steps: { label: string; status: string }[], label: string, status: string) {
  const index = steps.findIndex((item) => item.label === label)
  if (index < 0) return [...steps, { label, status }]
  const next = [...steps]
  next[index] = { label, status }
  return next
}

/** 把流式事件增量合并进一份 payload，让模块边到边显示。 */
function applyEvent(payload: QueryPayload, event: StreamEvent): QueryPayload {
  switch (event.type) {
    case 'keywords':
      return { ...payload, keywords: event.keywords }
    case 'tables':
      return { ...payload, selected_tables: event.selected }
    case 'sql':
      return { ...payload, sql: event.sql, warnings: event.warnings }
    case 'result':
      return {
        ...payload,
        columns: event.columns,
        rows: event.rows,
        row_count: event.row_count,
        duration_ms: event.duration_ms,
      }
    case 'chart':
      return { ...payload, chart: event.chart }
    case 'stats':
      return { ...payload, stats: event.stats }
    case 'answer':
      return { ...payload, answer: event.answer, followups: event.followups }
    case 'correction':
      return { ...payload, sql: event.sql }
    case 'error':
      return { ...payload, error: event.message }
    default:
      return payload
  }
}

/** 找到某条 AI 回复所回答的用户问题。 */
function findLastQuestion(messages: ChatMessage[], assistantId: number): string {
  const index = messages.findIndex((item) => item.id === assistantId)
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'user') return messages[i].content
  }
  return ''
}

function chunk<T>(list: T[], size: number): T[][] {
  const result: T[][] = []
  for (let i = 0; i < list.length; i += size) result.push(list.slice(i, i + size))
  return result
}
