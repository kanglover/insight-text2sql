import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Icon, type IconName } from './Icon'

/** 抽查一批常用的图标名，确保路径表没有空值（漏写 path 会渲染成空白方块）。 */
const SAMPLED: IconName[] = [
  'chat',
  'send',
  'close',
  'check',
  'search',
  'refresh',
  'star',
  'alert',
  'volume',
  'volumeOff',
  'microphone',
  'stop',
  'play',
  'pause',
]

describe('Icon', () => {
  it('渲染成内联 svg，不依赖图标字体', () => {
    const { container } = render(<Icon name="send" />)
    const svg = container.querySelector('svg')

    expect(svg).not.toBeNull()
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24')
    // 线性图标：不填充、描边跟文字颜色走
    expect(svg?.getAttribute('fill')).toBe('none')
    expect(svg?.getAttribute('stroke')).toBe('currentColor')
    expect(svg?.getAttribute('stroke-linecap')).toBe('round')
  })

  it('尺寸默认 16，可覆盖', () => {
    const { container: base } = render(<Icon name="chat" />)
    expect(base.querySelector('svg')?.getAttribute('width')).toBe('16')

    const { container: large } = render(<Icon name="chat" size={24} />)
    expect(large.querySelector('svg')?.getAttribute('width')).toBe('24')
    expect(large.querySelector('svg')?.getAttribute('height')).toBe('24')
  })

  it('描边宽度默认 1.8，可覆盖', () => {
    const { container } = render(<Icon name="chat" strokeWidth={2.5} />)
    expect(container.querySelector('svg')?.getAttribute('stroke-width')).toBe('2.5')
  })

  it('对读屏软件隐藏（图标永远有文字或 aria-label 配套）', () => {
    const { container } = render(<Icon name="chat" />)
    const svg = container.querySelector('svg')

    expect(svg?.getAttribute('aria-hidden')).toBe('true')
    expect(svg?.getAttribute('focusable')).toBe('false')
  })

  it('透传 className 与 style', () => {
    const { container } = render(
      <Icon name="chat" className="my-icon" style={{ color: 'red' }} />,
    )
    const svg = container.querySelector('svg')

    expect(svg?.classList.contains('my-icon')).toBe(true)
    expect(svg?.style.color).toBe('red')
  })

  it.each(SAMPLED)('%s 有非空的 path 数据', (name) => {
    const { container } = render(<Icon name={name} />)
    const d = container.querySelector('path')?.getAttribute('d') ?? ''

    expect(d.length).toBeGreaterThan(0)
    // 所有路径都以 moveTo 开头，空字符串或占位符会立刻暴露
    expect(d.startsWith('M')).toBe(true)
  })
})
