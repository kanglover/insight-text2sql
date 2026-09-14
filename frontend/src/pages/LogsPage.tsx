/**
 * 日志页：对应 demo 的「日志」。
 * 支持 7/30/90 天时间范围、关键词搜索、用户筛选、明细查看与 CSV 导出。
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { logApi } from '../api/endpoints'
import type { LogSummary, QueryLogItem } from '../types'
import { Icon } from '../components/Icon'
import { Pagination, SearchBox } from '../components/Controls'
import { Modal } from '../components/Modal'
import { formatDuration, formatNumber } from '../utils/format'

const RANGES = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 90, label: '近 90 天' },
]

export function LogsPage() {
  const [days, setDays] = useState(30)
  const [keyword, setKeyword] = useState('')
  const [userName, setUserName] = useState('')
  const [items, setItems] = useState<QueryLogItem[]>([])
  const [summary, setSummary] = useState<LogSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<QueryLogItem | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [rows, stats] = await Promise.all([
        logApi.list(days, keyword, userName, 500),
        logApi.summary(days),
      ])
      setItems(rows)
      setSummary(stats)
      setPage(1)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [days, keyword, userName])

  useEffect(() => {
    void load()
  }, [load])

  const users = useMemo(
    () => Array.from(new Set(items.map((item) => item.user_name).filter(Boolean))),
    [items],
  )

  const paged = useMemo(
    () => items.slice((page - 1) * pageSize, page * pageSize),
    [items, page, pageSize],
  )

  const exportCsv = () => {
    const header = ['时间', '用户', '问题', '状态', '耗时(ms)', 'Token', '行数', '生成方式', '命中表']
    const lines = items.map((item) =>
      [
        item.created_at,
        item.user_name,
        item.question,
        item.status,
        item.duration_ms,
        item.total_tokens,
        item.row_count,
        item.provider,
        item.tables_used.join('|'),
      ]
        .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
        .join(','),
    )
    // 加 BOM，避免 Excel 打开中文乱码
    const blob = new Blob([`\uFEFF${[header.join(','), ...lines].join('\n')}`], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `问数日志_近${days}天.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="page">
      <div className="breadcrumb">
        日志
        <span className="sep">/</span>
        <span className="current">问数日志</span>
      </div>

      <div className="stat-row">
        <StatCard label="总问数" value={formatNumber(summary?.total ?? 0)} />
        <StatCard label="成功率" value={`${summary?.success_rate ?? 100}%`} />
        <StatCard label="失败数" value={formatNumber(summary?.failed ?? 0)} />
        <StatCard label="平均耗时" value={formatDuration(summary?.avg_duration_ms ?? 0)} />
        <StatCard label="平均 Token" value={formatNumber(summary?.avg_tokens ?? 0)} />
      </div>

      <div className="card">
        <div className="toolbar">
          {RANGES.map((range) => (
            <button
              key={range.value}
              className={days === range.value ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'}
              onClick={() => setDays(range.value)}
            >
              {range.label}
            </button>
          ))}
          <span className="spacer" />
          <SearchBox value={keyword} onChange={setKeyword} placeholder="搜索问题内容" width={240} />
          <select
            className="select"
            style={{ width: 150, height: 34 }}
            value={userName}
            onChange={(event) => setUserName(event.target.value)}
            aria-label="按用户筛选"
          >
            <option value="">全部用户</option>
            {users.map((user) => (
              <option key={user} value={user}>
                {user}
              </option>
            ))}
          </select>
          <button className="btn btn-outline btn-sm" onClick={() => void load()} disabled={loading}>
            {loading ? <span className="spinner spinner-dark" /> : <Icon name="refresh" size={14} />}
            刷新
          </button>
          <button className="btn btn-outline btn-sm" onClick={exportCsv} disabled={!items.length}>
            <Icon name="download" size={14} />
            导出 CSV
          </button>
        </div>

        {error ? <div className="alert alert-error">{error}</div> : null}

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>用户</th>
                <th>问题</th>
                <th>状态</th>
                <th className="num">耗时</th>
                <th className="num">Token</th>
                <th className="num">行数</th>
                <th>生成方式</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {paged.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-state">
                      {loading ? '加载中…' : '暂无日志，先去「智能问数」问两个问题'}
                    </div>
                  </td>
                </tr>
              ) : (
                paged.map((item) => (
                  <tr key={item.id}>
                    <td className="nowrap mono">{item.created_at}</td>
                    <td>{item.user_name || '-'}</td>
                    <td className="cell-ellipsis" title={item.question}>
                      {item.question}
                    </td>
                    <td>
                      <span
                        className={item.status === '成功' ? 'tag tag-success' : 'tag tag-danger'}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="num">{formatDuration(item.duration_ms)}</td>
                    <td className="num">{formatNumber(item.total_tokens)}</td>
                    <td className="num">{formatNumber(item.row_count)}</td>
                    <td>
                      <span className="tag tag-primary">{item.provider || '-'}</span>
                    </td>
                    <td>
                      <button className="btn btn-text btn-xs" onClick={() => setDetail(item)}>
                        查看详情
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
          total={items.length}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      </div>

      <Modal
        open={Boolean(detail)}
        title="问数详情"
        subtitle={detail?.created_at}
        wide
        onClose={() => setDetail(null)}
        footer={
          <button className="btn btn-outline" onClick={() => setDetail(null)}>
            关闭
          </button>
        }
      >
        {detail ? (
          <>
            <div className="field">
              <label>问题</label>
              <div>{detail.question}</div>
            </div>
            <div className="row wrap mb-12">
              <span className="tag tag-primary">生成方式：{detail.provider || '-'}</span>
              <span className="tag">状态：{detail.status}</span>
              <span className="tag">耗时：{formatDuration(detail.duration_ms)}</span>
              <span className="tag">Token：{formatNumber(detail.total_tokens)}</span>
              <span className="tag">返回：{formatNumber(detail.row_count)} 行</span>
            </div>
            <div className="field">
              <label>命中数据表</label>
              <div className="chip-row">
                {detail.tables_used.length ? (
                  detail.tables_used.map((table) => (
                    <span className="tag tag-primary" key={table}>
                      {table}
                    </span>
                  ))
                ) : (
                  <span className="muted">无</span>
                )}
              </div>
            </div>
            <div className="field">
              <label>生成的 SQL</label>
              <pre className="sql-block">{detail.sql || '（无）'}</pre>
            </div>
            {detail.error ? (
              <div className="alert alert-error">
                <b>错误：</b>
                {detail.error}
              </div>
            ) : null}
          </>
        ) : null}
      </Modal>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}
