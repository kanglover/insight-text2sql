/**
 * 模型配置页：对应 demo 的「系统管理 → 模型配置」。
 *
 * 这里选择的模型会真正驱动后端推理链路：保存后，后端问数时会读取
 * 「选中模型」的 Base URL / 模型名 / API Key（缺省回退到环境变量）。
 * 页面里填的 API Key 会保存到数据库并用于实际推理（仅展示后四位提示）。
 */

import { useCallback, useEffect, useState } from 'react'
import { configApi, modelApi, type RuntimeConfig } from '../api/endpoints'
import type { ModelItem, ModelTestResult } from '../types'
import { Icon } from '../components/Icon'
import { Modal } from '../components/Modal'

export function ModelConfigPage() {
  const [models, setModels] = useState<ModelItem[]>([])
  const [runtime, setRuntime] = useState<RuntimeConfig | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  const [draft, setDraft] = useState({
    name: '',
    baseUrl: '',
    modelName: '',
    apiKey: '',
  })

  const load = useCallback(async () => {
    try {
      const [list, rt] = await Promise.all([modelApi.list(), configApi.runtime()])
      setModels(list)
      setRuntime(rt)
      const current = list.find((item) => item.selected)
      setSelectedId(current?.id ?? list[0]?.id ?? null)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const flash = (text: string) => {
    setNotice(text)
    window.setTimeout(() => setNotice(''), 2400)
  }

  const saveSelection = async () => {
    if (selectedId === null) return
    setSaving(true)
    setError('')
    try {
      await modelApi.select(selectedId)
      flash('已保存当前选择的模型')
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    setError('')
    try {
      // 优先用表单里的值；表单为空则测试后端当前生效的配置
      const picked = models.find((item) => item.id === selectedId)
      const result = await modelApi.test({
        baseUrl: draft.baseUrl || picked?.base_url || '',
        modelName: draft.modelName || picked?.model_name || '',
        apiKey: draft.apiKey,
      })
      setTestResult(result)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setTesting(false)
    }
  }

  const addModel = async () => {
    if (!draft.baseUrl.trim() || !draft.modelName.trim()) {
      setError('Base URL 与模型名称为必填项')
      return
    }
    setSaving(true)
    try {
      await modelApi.add({
        baseUrl: draft.baseUrl.trim(),
        modelName: draft.modelName.trim(),
        apiKey: draft.apiKey,
        name: draft.name.trim(),
      })
      setAddOpen(false)
      setDraft({ name: '', baseUrl: '', modelName: '', apiKey: '' })
      flash('模型已新增（已保存 API Key 用于推理）')
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const removeModel = async (model: ModelItem) => {
    try {
      await modelApi.remove(model.id)
      flash(`已删除 ${model.name}`)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const current = models.find((item) => item.id === selectedId)

  return (
    <div className="page">
      <div className="breadcrumb">
        系统管理
        <span className="sep">/</span>
        <span className="current">模型配置</span>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : null}
      {notice ? <div className="alert alert-success">{notice}</div> : null}

      <div className="card model-config">
        <div className="mc-title">模型配置</div>
        <div className="mc-subtitle">
          保存后，这里选中的模型会真正用于生成 SQL；没有填 Key 的模型会回退到后端环境变量 LLM_API_KEY。
        </div>

        <div className="mc-card">
          <div className="mc-card-hdr">
            <span className="mc-card-title">
              <Icon name="cpu" size={15} />
              语言模型
            </span>
            <div className="mc-row">
              <select
                className="select"
                style={{ width: 280 }}
                value={selectedId ?? ''}
                onChange={(event) => {
                  setSelectedId(Number(event.target.value))
                  setTestResult(null)
                }}
                aria-label="选择模型"
              >
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                    {model.selected ? '（当前）' : ''}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => setAddOpen(true)}
                type="button"
              >
                <Icon name="plus" size={14} />
                新增模型
              </button>
            </div>
          </div>
          <div className="mc-card-body">
            {current ? (
              <>
                <div>
                  Base URL：<span className="mono">{current.base_url}</span>
                </div>
                <div>
                  模型名称：<span className="mono">{current.model_name}</span>
                </div>
                <div>
                  API Key：
                  {current.api_key_hint ? (
                    <span className="mono">{current.api_key_hint}</span>
                  ) : (
                    '未填写（使用后端环境变量 LLM_API_KEY）'
                  )}
                </div>
                {current.note ? <div>备注：{current.note}</div> : null}
              </>
            ) : (
              <div>还没有可用的模型，点击「新增模型」添加一个。</div>
            )}
          </div>
        </div>

        <div className="mc-actions">
          <button
            className="btn btn-primary"
            onClick={() => void saveSelection()}
            disabled={saving || selectedId === null}
          >
            {saving ? <span className="spinner" /> : <Icon name="check" size={15} />}
            保存选择
          </button>
          <button
            className="btn btn-outline"
            onClick={() => void testConnection()}
            disabled={testing}
            type="button"
          >
            {testing ? <span className="spinner spinner-dark" /> : <Icon name="link" size={15} />}
            测试连接
          </button>
          {current ? (
            <button
              className="btn btn-ghost"
              onClick={() => void removeModel(current)}
              type="button"
            >
              <Icon name="trash" size={14} />
              删除该模型
            </button>
          ) : null}
        </div>

        {testResult ? (
          <div
            className={testResult.ok ? 'alert alert-success mt-16' : 'alert alert-error mt-16'}
            style={{ marginBottom: 0 }}
          >
            <b>{testResult.ok ? '连接成功' : '连接失败'}</b> · {testResult.message}
            {testResult.latency_ms ? ` · 耗时 ${testResult.latency_ms}ms` : ''}
            {testResult.checked === 'local' ? '（未发起远端请求）' : ''}
          </div>
        ) : null}
      </div>

      <div className="card">
        <div className="card-title">
          <Icon name="alert" size={17} />
          后端实际生效
        </div>
        <div className="card-desc">
          {runtime?.model.source === 'db_selected'
            ? '当前由上方「模型配置」中选中的模型驱动。'
            : '当前没有可用模型配置，回退到后端环境变量 LLM_PROVIDER / LLM_MODEL / LLM_BASE_URL / LLM_API_KEY。'}
        </div>
        <div className="stat-row" style={{ marginBottom: 0 }}>
          <div className="stat-card">
            <div className="label">提供方</div>
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
            <div className="label">Base URL</div>
            <div className="value mono" style={{ fontSize: 13, wordBreak: 'break-all' }}>
              {runtime?.model.base_url ?? '-'}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Temperature</div>
            <div className="value" style={{ fontSize: 17 }}>
              {runtime?.model.temperature ?? '-'}
            </div>
          </div>
        </div>
      </div>

      <Modal
        open={addOpen}
        title="新增模型"
        subtitle="支持任意 OpenAI 兼容协议的服务"
        onClose={() => setAddOpen(false)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setAddOpen(false)}>
              取消
            </button>
            <button className="btn btn-primary" onClick={() => void addModel()} disabled={saving}>
              保存
            </button>
          </>
        }
      >
        <div className="field">
          <label htmlFor="m-name">显示名称</label>
          <input
            id="m-name"
            className="input"
            placeholder="例如：GLM-4-Plus（智谱）"
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="m-base">Base URL</label>
          <input
            id="m-base"
            className="input"
            placeholder="https://api.example.com/v1"
            value={draft.baseUrl}
            onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="m-model">模型名称</label>
          <input
            id="m-model"
            className="input"
            placeholder="例如：glm-4-plus"
            value={draft.modelName}
            onChange={(event) => setDraft({ ...draft, modelName: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="m-key">API Key（保存后用于实际推理，缺省回退环境变量）</label>
          <input
            id="m-key"
            className="input"
            type="password"
            placeholder="将保存到数据库，供选中模型实际调用；页面仅展示后四位"
            value={draft.apiKey}
            onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
          />
        </div>
      </Modal>
    </div>
  )
}
