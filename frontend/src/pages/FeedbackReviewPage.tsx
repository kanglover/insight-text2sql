/**
 * 回复校对页：对应 demo 的「反馈管理 → 回复校对」。
 * 列表 + 搜索 + 状态筛选 + 分页 + 处理（标记状态、写备注）。
 */

import { useCallback, useEffect, useState } from 'react'
import { feedbackApi } from '../api/endpoints'
import type { FeedbackItem, FeedbackStats } from '../types'
import { Icon } from '../components/Icon'
import { Pagination, SearchBox } from '../components/Controls'
import { Modal } from '../components/Modal'
import { formatNumber } from '../utils/format'

const STATUS_TABS = [
  { value: 'all', label: '全部' },
  { value: '待处理', label: '待处理' },
  { value: '已处理', label: '已处理' },
]

export function FeedbackReviewPage() {
  const [items, setItems] = useState<FeedbackItem[]>([])
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [status, setStatus] = useState('all')
  const [keyword, setKeyword] = useState('')
  const [userKeyword, setUserKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<FeedbackItem | null>(null)
  const [editStatus, setEditStatus] = useState('待处理')
  const [editRemark, setEditRemark] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [data, stat] = await Promise.all([
        feedbackApi.list({ status, keyword, userKeyword, page, pageSize }),
        feedbackApi.stats(),
      ])
      setItems(data.items)
      setTotal(data.total)
      setStats(stat)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [status, keyword, userKeyword, page, pageSize])

  useEffect(() => {
    void load()
  }, [load])

  const openEditor = (item: FeedbackItem) => {
    setEditing(item)
    setEditStatus(item.status || '待处理')
    setEditRemark(item.remark ?? '')
  }

  const submitEdit = async () => {
    if (!editing) return
    try {
      await feedbackApi.update(editing.id, editStatus, editRemark)
      setEditing(null)
      setNotice('反馈已更新')
      window.setTimeout(() => setNotice(''), 2200)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="page">
      <div className="breadcrumb">
        反馈管理
        <span className="sep">/</span>
        <span className="current">回复校对</span>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <div className="label">反馈总数</div>
          <div className="value">{formatNumber(stats?.total ?? 0)}</div>
        </div>
        <div className="stat-card">
          <div className="label">待处理</div>
          <div className="value" style={{ color: '#b45309' }}>
            {formatNumber(stats?.pending ?? 0)}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">近 7 天</div>
          <div className="value">{formatNumber(stats?.recent ?? 0)}</div>
        </div>
      </div>

      <div className="card">
        {error ? <div className="alert alert-error">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}

        <div className="toolbar">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              className={status === tab.value ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'}
              onClick={() => {
                setStatus(tab.value)
                setPage(1)
              }}
            >
              {tab.label}
            </button>
          ))}
          <span className="spacer" />
          <SearchBox
            value={keyword}
            onChange={(value) => {
              setKeyword(value)
              setPage(1)
            }}
            placeholder="搜索问题"
            width={220}
          />
          <SearchBox
            value={userKeyword}
            onChange={(value) => {
              setUserKeyword(value)
              setPage(1)
            }}
            placeholder="搜索用户"
            width={180}
          />
          <button className="btn btn-outline btn-sm" onClick={() => void load()} disabled={loading}>
            {loading ? <span className="spinner spinner-dark" /> : <Icon name="refresh" size={14} />}
            刷新
          </button>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>提交时间</th>
                <th>用户</th>
                <th>问题</th>
                <th>反馈内容</th>
                <th>状态</th>
                <th>处理备注</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-state">
                      {loading ? '加载中…' : '暂无反馈。在问数页点击「数据有误」即可提交'}
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id}>
                    <td className="nowrap mono">{item.created_at}</td>
                    <td>{item.user_name || '-'}</td>
                    <td className="cell-ellipsis" title={item.question}>
                      {item.question}
                    </td>
                    <td className="cell-ellipsis" title={item.message}>
                      {item.message}
                    </td>
                    <td>
                      <span
                        className={item.status === '已处理' ? 'tag tag-success' : 'tag tag-warning'}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="cell-ellipsis" title={item.remark}>
                      {item.remark || <span className="muted">-</span>}
                    </td>
                    <td>
                      <button className="btn btn-text btn-xs" onClick={() => openEditor(item)}>
                        处理
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      </div>

      <Modal
        open={Boolean(editing)}
        title="处理反馈"
        subtitle={`#${editing?.id ?? ''} · ${editing?.created_at ?? ''}`}
        wide
        onClose={() => setEditing(null)}
        footer={
          <>
            <button className="btn btn-text" onClick={() => setEditing(null)}>
              取消
            </button>
            <button className="btn btn-primary" onClick={() => void submitEdit()}>
              保存
            </button>
          </>
        }
      >
        {editing ? (
          <>
            <div className="orig-block">
              <div className="ob-hdr">用户问题</div>
              <div className="ob-body">{editing.question}</div>
            </div>
            <div className="orig-block">
              <div className="ob-hdr">AI 当时的回复</div>
              <div className="ob-body">
                {editing.ai_reply || <span className="muted">（未记录回复内容）</span>}
              </div>
            </div>
            <div className="orig-block">
              <div className="ob-hdr">用户反馈</div>
              <div className="ob-body">{editing.message}</div>
            </div>

            <div className="field">
              <label htmlFor="fb-status">处理状态</label>
              <select
                id="fb-status"
                className="select"
                value={editStatus}
                onChange={(event) => setEditStatus(event.target.value)}
              >
                <option value="待处理">待处理</option>
                <option value="已处理">已处理</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="fb-remark">处理备注</label>
              <textarea
                id="fb-remark"
                className="textarea"
                placeholder="例如：口径有误，已修正「完成率」指标定义"
                value={editRemark}
                onChange={(event) => setEditRemark(event.target.value)}
                maxLength={1000}
              />
            </div>
          </>
        ) : null}
      </Modal>
    </div>
  )
}
