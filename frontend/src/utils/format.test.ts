import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  copyText,
  formatAmount,
  formatDuration,
  formatNumber,
  formatRelative,
  truncate,
} from './format'

/** 相对当前时间的 ISO 串，避免用例依赖固定日期。 */
const ago = (ms: number) => new Date(Date.now() - ms).toISOString()

describe('formatNumber', () => {
  it('空值统一显示为短横线', () => {
    expect(formatNumber(null)).toBe('-')
    expect(formatNumber(undefined)).toBe('-')
    expect(formatNumber('')).toBe('-')
  })

  it('字符串原样返回，不做二次解析', () => {
    expect(formatNumber('1,234.5')).toBe('1,234.5')
    expect(formatNumber('暂无')).toBe('暂无')
  })

  it('整数加千分位且不带小数', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(-1234)).toBe('-1,234')
  })

  it('小数保留一位', () => {
    expect(formatNumber(12.34)).toBe('12.3')
    expect(formatNumber(0.06)).toBe('0.1')
  })

  it('NaN 不会崩，退化成原样字符串', () => {
    expect(formatNumber(Number.NaN)).toBe('NaN')
  })
})

describe('formatAmount', () => {
  it('加人民币符号', () => {
    expect(formatAmount(1200)).toBe('¥1,200')
  })

  it('空值不加符号', () => {
    expect(formatAmount(null)).toBe('-')
  })
})

describe('formatDuration', () => {
  it('小于一秒用毫秒', () => {
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(999)).toBe('999ms')
  })

  it('负数与假值按 0 处理', () => {
    expect(formatDuration(-5)).toBe('0ms')
    expect(formatDuration(Number.NaN)).toBe('0ms')
  })

  it('超过一秒转秒并保留两位', () => {
    expect(formatDuration(1000)).toBe('1.00s')
    expect(formatDuration(12_345)).toBe('12.35s')
  })
})

describe('formatRelative', () => {
  it('空串返回空串', () => {
    expect(formatRelative('')).toBe('')
  })

  it('无法解析时原样返回，不显示 Invalid Date', () => {
    expect(formatRelative('not-a-date')).toBe('not-a-date')
  })

  it('一分钟内是「刚刚」', () => {
    expect(formatRelative(ago(30_000))).toBe('刚刚')
  })

  it('分钟 / 小时 / 天逐级换算', () => {
    expect(formatRelative(ago(5 * 60_000))).toBe('5 分钟前')
    expect(formatRelative(ago(3 * 3_600_000))).toBe('3 小时前')
    expect(formatRelative(ago(2 * 86_400_000))).toBe('2 天前')
  })

  it('超过 30 天回落到具体日期', () => {
    expect(formatRelative('2020-01-02 03:04:05')).toBe('2020-01-02')
  })

  it('兼容后端「日期 时间」带空格的格式（按本地时区解析）', () => {
    const pad = (n: number) => String(n).padStart(2, '0')
    const d = new Date(Date.now() - 10 * 60_000)
    const local = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
      d.getHours(),
    )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`

    expect(formatRelative(local)).toBe('10 分钟前')
  })
})

describe('truncate', () => {
  it('未超长时原样返回并去掉首尾空白', () => {
    expect(truncate('  各经营单元  ')).toBe('各经营单元')
  })

  it('超长时截断并加省略号', () => {
    const long = '一二三四五六七八九十'
    expect(truncate(long, 4)).toBe('一二三四…')
  })

  it('刚好等于上限不截断', () => {
    expect(truncate('abcd', 4)).toBe('abcd')
  })

  it('空值返回空串', () => {
    expect(truncate('')).toBe('')
  })
})

describe('copyText', () => {
  function setClipboard(value: unknown) {
    Object.defineProperty(navigator, 'clipboard', { value, configurable: true, writable: true })
  }

  function setExecCommand(result: boolean) {
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => result),
      configurable: true,
      writable: true,
    })
  }

  afterEach(() => {
    setClipboard(undefined)
  })

  it('优先使用 clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    setClipboard({ writeText })

    await expect(copyText('sql')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('sql')
  })

  it('clipboard 不可用时退回 execCommand，并清理临时节点', async () => {
    setClipboard(undefined)
    setExecCommand(true)

    await expect(copyText('sql')).resolves.toBe(true)
    expect(document.querySelectorAll('textarea')).toHaveLength(0)
  })

  it('execCommand 失败时返回 false', async () => {
    setClipboard(undefined)
    setExecCommand(false)

    await expect(copyText('sql')).resolves.toBe(false)
  })

  it('写入抛错时吞掉异常，返回 false', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) })

    await expect(copyText('sql')).resolves.toBe(false)
  })
})
