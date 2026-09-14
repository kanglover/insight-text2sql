import type { ReactNode } from 'react'
import { formatNumber } from '../utils/format'

type Cell = number | string | null

interface DataTableProps {
  columns: string[]
  rows: Cell[][]
  /** 超过这个行数只展示前 N 行，其余用一行提示带过。 */
  maxRows?: number
  className?: string
}

/** 结果表：数值列自动右对齐，避免中文表头 + 数字混排时对不齐。 */
export function DataTable({ columns, rows, maxRows, className }: DataTableProps) {
  if (!columns.length) return null
  const visible = typeof maxRows === 'number' ? rows.slice(0, maxRows) : rows
  const hidden = rows.length - visible.length

  return (
    <div className={`table-wrap ${className ?? ''}`}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((_, columnIndex) => {
                const cell = row[columnIndex]
                const numeric = typeof cell === 'number'
                return (
                  <td key={columnIndex} className={numeric ? 'num' : ''}>
                    {numeric ? formatNumber(cell) : (cell ?? '-')}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {hidden > 0 ? (
        <div className="empty-state" style={{ padding: '10px' }}>
          另有 {hidden} 行未展示，可通过 SQL 或日志页查看完整结果
        </div>
      ) : null}
    </div>
  )
}

interface ModuleProps {
  index: number
  title: string
  children: ReactNode
}

/** AI 回复里的编号模块（对应 demo 的 1/2/3/4 小节）。 */
export function Module({ index, title, children }: ModuleProps) {
  return (
    <div className="qa-ai-module">
      <div className="mod-title">
        <span className="mod-num">{index}</span>
        {title}
      </div>
      <div className="mod-body">{children}</div>
    </div>
  )
}

export function DotList({ items }: { items: ReactNode[] }) {
  const list = items.filter(Boolean)
  if (!list.length) return null
  return (
    <>
      {list.map((item, index) => (
        <div className="dot-li" key={index}>
          <span>{item}</span>
        </div>
      ))}
    </>
  )
}
