import { Icon } from './Icon'

interface ToggleProps {
  checked: boolean
  onChange?: (next: boolean) => void
  disabled?: boolean
  label?: string
}

export function Toggle({ checked, onChange, disabled, label }: ToggleProps) {
  return (
    <button
      type="button"
      className={checked ? 'toggle on' : 'toggle'}
      onClick={() => !disabled && onChange?.(!checked)}
      disabled={disabled}
      role="switch"
      aria-checked={checked}
      aria-label={label ?? '开关'}
    />
  )
}

interface SearchBoxProps {
  value: string
  onChange: (next: string) => void
  placeholder?: string
  width?: number
}

export function SearchBox({ value, onChange, placeholder, width }: SearchBoxProps) {
  return (
    <div className="search-box" style={width ? { maxWidth: width } : undefined}>
      <Icon name="search" size={15} />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? '搜索'}
        aria-label={placeholder ?? '搜索'}
      />
    </div>
  )
}

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange?: (size: number) => void
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const pages: number[] = []
  const start = Math.max(1, Math.min(page - 2, pageCount - 4))
  const end = Math.min(pageCount, start + 4)
  for (let i = start; i <= end; i += 1) pages.push(i)

  return (
    <div className="pagination">
      <span>
        共 {total} 条 · 第 {page}/{pageCount} 页
      </span>
      {onPageSizeChange ? (
        <select
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          aria-label="每页条数"
        >
          {[10, 20, 50].map((size) => (
            <option key={size} value={size}>
              {size} 条/页
            </option>
          ))}
        </select>
      ) : null}
      <div className="page-btns">
        <button onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="上一页">
          <Icon name="chevronLeft" size={14} />
        </button>
        {pages.map((item) => (
          <button
            key={item}
            className={item === page ? 'active' : ''}
            onClick={() => onPageChange(item)}
          >
            {item}
          </button>
        ))}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label="下一页"
        >
          <Icon name="chevronRight" size={14} />
        </button>
      </div>
    </div>
  )
}
