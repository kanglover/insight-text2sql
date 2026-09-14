/** 展示层格式化工具。 */

/** 千分位。整数不带小数，小数保留 1 位，和 demo 的口径一致。 */
export function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string') return value
  if (typeof value !== 'number' || Number.isNaN(value)) return String(value ?? '-')
  if (Number.isInteger(value)) return value.toLocaleString('zh-CN')
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

/** 金额（万元）展示。 */
export function formatAmount(value: unknown): string {
  const text = formatNumber(value)
  return text === '-' ? text : `¥${text}`
}

/** 毫秒转可读耗时。 */
export function formatDuration(ms: number): string {
  if (!ms || ms < 0) return '0ms'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/** 相对时间：2 分钟前 / 3 小时前 / 具体日期。 */
export function formatRelative(iso: string): string {
  if (!iso) return ''
  const time = new Date(iso.replace(' ', 'T')).getTime()
  if (Number.isNaN(time)) return iso
  const diff = Date.now() - time
  const minute = 60_000
  if (diff < minute) return '刚刚'
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`
  if (diff < 30 * 24 * 60 * minute) return `${Math.floor(diff / (24 * 60 * minute))} 天前`
  return iso.slice(0, 10)
}

/** 从会话标题里截断，避免长标题撑破侧栏。 */
export function truncate(text: string, max = 18): string {
  const value = (text ?? '').trim()
  return value.length > max ? `${value.slice(0, max)}…` : value
}

/** 复制到剪贴板，带 http 环境降级。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
