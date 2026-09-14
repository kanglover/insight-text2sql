/**
 * 应用配置页：对应 demo 的「系统管理 → 应用配置」。
 *
 * 六个开关 + 开场白与推荐问题设置。配置存在后端 app_config 里，
 * 前端只做局部 patch，避免并发写覆盖。
 */

import { useCallback, useEffect, useState } from 'react'
import { configApi, type RuntimeConfig } from '../api/endpoints'
import type { AppConfig } from '../types'
import { Icon, type IconName } from '../components/Icon'
import { Toggle } from '../components/Controls'
import { Modal } from '../components/Modal'

interface CardSpec {
  key: keyof AppConfig
  name: string
  desc: string
  icon: IconName
  iconBg: string
  iconColor: string
  settable?: 'greeting' | 'hot'
}

const CARDS: CardSpec[] = [
  {
    key: 'greeting',
    name: '开场白',
    desc: '开启后，新对话首屏展示欢迎语与推荐问题',
    icon: 'chat',
    iconBg: '#EEF2FF',
    iconColor: '#2F54EB',
    settable: 'greeting',
  },
  {
    key: 'suggestions',
    name: '延伸问题',
    desc: '开启后，AI 回复下方自动生成 3 条相关延伸问题',
    icon: 'sparkle',
    iconBg: '#F0FDF4',
    iconColor: '#16A34A',
  },
  {
    key: 'tts',
    name: '文字转语音',
    desc: '开启后，支持把 AI 回复转成语音播报',
    icon: 'play',
    iconBg: '#FFF7ED',
    iconColor: '#EA580C',
  },
  {
    key: 'stt',
    name: '语音转文字',
    desc: '开启后，支持用语音输入问题',
    icon: 'bell',
    iconBg: '#FEF2F2',
    iconColor: '#DC2626',
  },
  {
    key: 'hotRecommend',
    name: '常问推荐',
    desc: '按提问频次自动统计「常问」，出现在输入框的快捷面板里',
    icon: 'chart',
    iconBg: '#F5F3FF',
    iconColor: '#7C3AED',
    settable: 'hot',
  },
  {
    key: 'modelConfig',
    name: '模型配置',
    desc: '开启后，顶栏展示当前生效的模型信息',
    icon: 'cpu',
    iconBg: '#ECFEFF',
    iconColor: '#0891B2',
  },
]

export function AppConfigPage() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [runtime, setRuntime] = useState<RuntimeConfig | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [greetingModal, setGreetingModal] = useState(false)
  const [hotModal, setHotModal] = useState(false)
  const [greetingDraft, setGreetingDraft] = useState('')
  const [questionsDraft, setQuestionsDraft] = useState('')
  const [thresholdDraft, setThresholdDraft] = useState(3)

  const load = useCallback(async () => {
    try {
      const [app, rt] = await Promise.all([configApi.getApp(), configApi.runtime()])
      setConfig(app)
      setRuntime(rt)
      setGreetingDraft(app.greetingText)
      setQuestionsDraft(app.greetingQuestions.join('\n'))
      setThresholdDraft(app.hotThreshold)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const patch = async (body: Partial<AppConfig>, tip = '配置已保存') => {
    setSaved('')
    setError('')
    try {
      const next = await configApi.patchApp(body)
      setConfig(next)
      setSaved(tip)
      window.setTimeout(() => setSaved(''), 2200)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!config) {
    return (
      <div className="page">
        {error ? <div className="alert alert-error">{error}</div> : <div className="empty-state">加载中…</div>}
      </div>
    )
  }

  return (
    <div className="page">
      <div className="breadcrumb">
        系统管理
        <span className="sep">/</span>
        <span className="current">应用配置</span>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : null}
      {saved ? <div className="alert alert-success">{saved}</div> : null}

      <div className="card">
        <div className="card-title">
          <Icon name="sliders" size={17} />
          应用能力开关
        </div>
        <div className="card-desc">开关立即生效，配置持久化在后端，重启不丢失。</div>

        <div className="app-config-grid">
          {CARDS.map((card) => (
            <div className="app-card" key={String(card.key)}>
              <div className="app-card-top">
                <span
                  className="app-card-icon"
                  style={{ background: card.iconBg, color: card.iconColor }}
                >
                  <Icon name={card.icon} size={17} />
                </span>
                <span className="app-card-name">{card.name}</span>
                <div className="app-card-actions">
                  {card.settable === 'greeting' ? (
                    <button
                      className="app-card-set"
                      title="设置开场白"
                      onClick={() => setGreetingModal(true)}
                    >
                      <Icon name="settings" size={15} />
                    </button>
                  ) : null}
                  {card.settable === 'hot' ? (
                    <button
                      className="app-card-set"
                      title="设置常问阈值"
                      onClick={() => setHotModal(true)}
                    >
                      <Icon name="settings" size={15} />
                    </button>
                  ) : null}
                  <Toggle
                    checked={Boolean(config[card.key])}
                    label={card.name}
                    onChange={(next) => void patch({ [card.key]: next } as Partial<AppConfig>)}
                  />
                </div>
              </div>
              <div className="app-card-desc">{card.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <Icon name="cpu" size={17} />
          后端真实生效配置
        </div>
        <div className="card-desc">
          这一块来自后端环境变量与启动参数，和上面的页面开关相互独立，避免「改了页面以为生效」。
        </div>
        <div className="stat-row" style={{ marginBottom: 0 }}>
          <div className="stat-card">
            <div className="label">LLM 提供方</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.model.provider ?? '-'}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">模型</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.model.model_name ?? '-'}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">密钥</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.model.configured ? '已配置' : '未配置'}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">SQL 行数上限</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.sql.row_limit ?? '-'}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">SQL 超时</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.sql.timeout_seconds ?? '-'}s
            </div>
          </div>
          <div className="stat-card">
            <div className="label">召回 TopK / 表上限</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime ? `${runtime.recall.top_k} / ${runtime.recall.max_tables}` : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* ---- 开场白设置 ---- */}
      <Modal
        open={greetingModal}
        title="开场白设置"
        subtitle="首屏欢迎语与推荐问题"
        onClose={() => setGreetingModal(false)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setGreetingModal(false)}>
              取消
            </button>
            <button
              className="btn btn-primary"
              onClick={async () => {
                await patch(
                  {
                    greetingText: greetingDraft,
                    greetingQuestions: questionsDraft
                      .split('\n')
                      .map((item) => item.trim())
                      .filter(Boolean)
                      .slice(0, config.maxGreetingQuestions),
                  },
                  '开场白已保存',
                )
                setGreetingModal(false)
              }}
            >
              保存
            </button>
          </>
        }
      >
        <div className="field">
          <label htmlFor="greeting-text">欢迎语</label>
          <textarea
            id="greeting-text"
            className="textarea"
            value={greetingDraft}
            onChange={(event) => setGreetingDraft(event.target.value)}
            maxLength={500}
          />
        </div>
        <div className="field">
          <label htmlFor="greeting-questions">推荐问题</label>
          <textarea
            id="greeting-questions"
            className="textarea"
            value={questionsDraft}
            onChange={(event) => setQuestionsDraft(event.target.value)}
          />
          <span className="hint">
            每行一条，最多 {config.maxGreetingQuestions} 条。首屏会按两列展示。
          </span>
        </div>
      </Modal>

      {/* ---- 常问设置 ---- */}
      <Modal
        open={hotModal}
        title="常问推荐设置"
        subtitle="按提问频次统计，达到阈值的问题会出现在「常问」里"
        onClose={() => setHotModal(false)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setHotModal(false)}>
              取消
            </button>
            <button
              className="btn btn-primary"
              onClick={async () => {
                await patch({ hotThreshold: thresholdDraft }, '常问阈值已保存')
                setHotModal(false)
              }}
            >
              保存
            </button>
          </>
        }
      >
        <div className="field">
          <label htmlFor="hot-threshold">触发阈值（被问到的次数）</label>
          <input
            id="hot-threshold"
            className="input"
            type="number"
            min={1}
            max={100}
            value={thresholdDraft}
            onChange={(event) => setThresholdDraft(Number(event.target.value))}
          />
          <span className="hint">当前没有达到阈值的问题时，会展示一组预置推荐问题兜底。</span>
        </div>
        <div className="field">
          <label>当前收藏</label>
          <div className="chip-row">
            {config.favorites.length ? (
              config.favorites.map((item) => (
                <span className="tag tag-warning" key={item}>
                  {item}
                </span>
              ))
            ) : (
              <span className="muted">还没有收藏问题</span>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}
