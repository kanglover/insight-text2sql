import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render } from '@testing-library/react'

/**
 * echarts 依赖真实 canvas，jsdom 里跑不起来。
 * 这里把它的入口 mock 掉，只断言「我们交给 echarts 的 option 是什么」——
 * 双 Y 轴、配色、旋转这些决策都在我们的代码里，正好是需要被锁住的部分。
 */
const mocks = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  init: vi.fn(),
}))

vi.mock('echarts/core', () => ({ use: vi.fn(), init: mocks.init }))
vi.mock('echarts/charts', () => ({ BarChart: {}, LineChart: {}, PieChart: {} }))
vi.mock('echarts/components', () => ({
  GridComponent: {},
  LegendComponent: {},
  TitleComponent: {},
  TooltipComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import { ChartView } from './ChartView'
import type { ChartSpec } from '../types'

// 配置里开了 restoreMocks，模块级 mock 的实现会在每个用例前被清掉，需要重装
beforeEach(() => {
  mocks.init.mockImplementation(() => ({
    setOption: mocks.setOption,
    resize: mocks.resize,
    dispose: mocks.dispose,
  }))
})

/**
 * echarts 的 option 本身类型极宽松（EChartsCoreOption 全是可选 any），
 * 这里直接用宽松类型承接：断言关心的是「我们传了什么值」，类型系统帮不上忙。
 */
type Option = Record<string, any>

function lastOption(): Option {
  const calls = mocks.setOption.mock.calls
  return calls[calls.length - 1][0] as Option
}

describe('ChartView — 指标卡', () => {
  it('metric 类型渲染数值卡片，不初始化 echarts', () => {
    render(
      <ChartView
        spec={{ type: 'metric', metrics: [{ label: '总收入', value: 2180 }] }}
      />,
    )

    expect(document.querySelector('.metric-box')).not.toBeNull()
    expect(document.querySelector('.metric-box .label')).toHaveTextContent('总收入')
    expect(document.querySelector('.metric-box .value')).toHaveTextContent('2,180')
    expect(mocks.init).not.toHaveBeenCalled()
  })

  it('多个指标并排，空数组也不崩', () => {
    const { container, rerender } = render(
      <ChartView
        spec={{
          type: 'metric',
          metrics: [
            { label: '总收入', value: 2180 },
            { label: '完成率', value: '78.1%' },
          ],
        }}
      />,
    )
    expect(container.querySelectorAll('.metric-box')).toHaveLength(2)

    rerender(<ChartView spec={{ type: 'metric', metrics: [] }} />)
    expect(container.querySelectorAll('.metric-box')).toHaveLength(0)
  })
})

describe('ChartView — 饼图', () => {
  const pie: ChartSpec = {
    type: 'pie',
    name: '行业占比',
    data: [
      { name: '制造业', value: 40 },
      { name: '金融业', value: 60 },
    ],
  }

  it('把 data 映射成 echarts 的 name/value 结构', () => {
    render(<ChartView spec={pie} />)
    const option = lastOption()

    expect(option.series[0].type).toBe('pie')
    expect(option.series[0].data).toEqual([
      { name: '制造业', value: 40 },
      { name: '金融业', value: 60 },
    ])
  })

  it('饼图高度固定 300，不随分片数量增长', () => {
    const { container } = render(<ChartView spec={pie} />)
    expect((container.querySelector('.chart-canvas') as HTMLElement).style.height).toBe('300px')
  })

  it('图例放底部，tooltip 用统一的数字格式', () => {
    render(<ChartView spec={pie} />)
    const option = lastOption()

    expect(option.legend.bottom).toBe(0)
    expect(option.tooltip.trigger).toBe('item')
    expect(option.tooltip.valueFormatter(12345)).toBe('12,345')
  })
})

describe('ChartView — 柱状 / 折线', () => {
  const bar: ChartSpec = {
    type: 'bar',
    x: 'org_name',
    series: ['收入额'],
    data: [
      { name: '北京', 收入额: 1200 },
      { name: '上海', 收入额: 980 },
    ],
  }

  it('单度量时只有一根 Y 轴', () => {
    render(<ChartView spec={bar} />)
    const option = lastOption()

    expect(Array.isArray(option.yAxis)).toBe(false)
    expect(option.yAxis.type).toBe('value')
    expect(option.series[0].type).toBe('bar')
    expect(option.series[0].yAxisIndex).toBe(0)
    expect(option.grid.right).toBe(16)
  })

  it('x 轴用行里的 name 字段作为类目', () => {
    render(<ChartView spec={bar} />)
    expect(lastOption().xAxis.data).toEqual(['北京', '上海'])
  })

  it('柱状图给上方圆角，避免直角显得比数据"重"', () => {
    render(<ChartView spec={bar} />)
    expect(lastOption().series[0].itemStyle.borderRadius).toEqual([4, 4, 0, 0])
  })

  it('line 类型走折线并开启平滑', () => {
    render(
      <ChartView
        spec={{
          type: 'line',
          x: '月份',
          series: ['收入额'],
          data: [{ name: '1 月', 收入额: 100 }],
        }}
      />,
    )
    const series = lastOption().series[0]

    expect(series.type).toBe('line')
    expect(series.smooth).toBe(true)
    expect(series.showSymbol).toBe(true)
  })

  it('类目超过 20 个时隐藏数据点，避免糊成一片', () => {
    const data = Array.from({ length: 25 }, (_, index) => ({ name: `M${index}`, 收入额: index }))
    render(<ChartView spec={{ type: 'line', x: '月份', series: ['收入额'], data }} />)
    expect(lastOption().series[0].showSymbol).toBe(false)
  })

  it('类目越多画布越高，给旋转标签留空间', () => {
    const make = (count: number): ChartSpec => ({
      type: 'bar',
      x: 'org_name',
      series: ['收入额'],
      data: Array.from({ length: count }, (_, index) => ({ name: `单元${index}`, 收入额: index })),
    })

    const { container, rerender } = render(<ChartView spec={make(5)} />)
    const heightOf = () => (container.querySelector('.chart-canvas') as HTMLElement).style.height
    expect(heightOf()).toBe('300px')

    rerender(<ChartView spec={make(10)} />)
    expect(heightOf()).toBe('360px')

    rerender(<ChartView spec={make(17)} />)
    expect(heightOf()).toBe('420px')
  })

  it('标签旋转角度随类目数分档', () => {
    const make = (count: number): ChartSpec => ({
      type: 'bar',
      x: 'org_name',
      series: ['收入额'],
      data: Array.from({ length: count }, (_, index) => ({ name: `单元${index}`, 收入额: index })),
    })

    const { rerender } = render(<ChartView spec={make(5)} />)
    expect(lastOption().xAxis.axisLabel.rotate).toBe(0)

    rerender(<ChartView spec={make(10)} />)
    expect(lastOption().xAxis.axisLabel.rotate).toBe(28)

    rerender(<ChartView spec={make(17)} />)
    expect(lastOption().xAxis.axisLabel.rotate).toBe(45)
  })
})

describe('ChartView — 双 Y 轴（金额 + 完成率）', () => {
  const dual: ChartSpec = {
    type: 'bar',
    x: 'org_name',
    series: ['收入额', '完成率'],
    data: [
      { name: '北京', 收入额: 1200, 完成率: 78.1 },
      { name: '上海', 收入额: 980, 完成率: 65.2 },
    ],
  }

  it('比率与数量并存时拆成两根 Y 轴，比率在右侧', () => {
    render(<ChartView spec={dual} />)
    const option = lastOption()

    expect(Array.isArray(option.yAxis)).toBe(true)
    expect(option.yAxis).toHaveLength(2)
    expect(option.yAxis[0].name).toBe('金额 / 数量')
    expect(option.yAxis[1].name).toBe('比率(%)')
    expect(option.yAxis[1].position).toBe('right')
    expect(option.yAxis[1].axisLabel.formatter).toBe('{value}%')
    // 右侧轴不画横向网格线，否则和左轴叠在一起很脏
    expect(option.yAxis[1].splitLine.show).toBe(false)
  })

  it('比率序列改画折线并挂到右轴', () => {
    render(<ChartView spec={dual} />)
    const [valueSeries, ratioSeries] = lastOption().series

    expect(valueSeries.type).toBe('bar')
    expect(valueSeries.yAxisIndex).toBe(0)
    expect(ratioSeries.type).toBe('line')
    expect(ratioSeries.yAxisIndex).toBe(1)
    expect(ratioSeries.smooth).toBe(true)
    expect(ratioSeries.showSymbol).toBe(true)
  })

  it('比率固定用橙色，数量按调色板顺序取色', () => {
    render(<ChartView spec={dual} />)
    expect(lastOption().color).toEqual(['#2f54eb', '#f5a623'])
  })

  it('双轴时右侧留出更多边距放百分比刻度', () => {
    render(<ChartView spec={dual} />)
    expect(lastOption().grid.right).toBe(24)
  })

  it('「占比 / 比例」等同义指标同样识别为比率', () => {
    render(
      <ChartView
        spec={{
          type: 'bar',
          x: 'org_name',
          series: ['收入额', '毛利率', '占比'],
          data: [{ name: '北京', 收入额: 10, 毛利率: 30, 占比: 5 }],
        }}
      />,
    )
    const option = lastOption()

    expect(option.yAxis).toHaveLength(2)
    expect(option.series.map((item: { yAxisIndex: number }) => item.yAxisIndex)).toEqual([0, 1, 1])
  })

  it('只有比率没有数量时不拆轴（否则右轴是空的）', () => {
    render(
      <ChartView
        spec={{
          type: 'bar',
          x: 'org_name',
          series: ['完成率', '占比'],
          data: [{ name: '北京', 完成率: 78.1, 占比: 12 }],
        }}
      />,
    )
    const option = lastOption()

    expect(Array.isArray(option.yAxis)).toBe(false)
    expect(option.series.every((item: { yAxisIndex: number }) => item.yAxisIndex === 0)).toBe(true)
  })
})

describe('ChartView — 生命周期', () => {
  const spec: ChartSpec = {
    type: 'bar',
    x: 'org_name',
    series: ['收入额'],
    data: [{ name: '北京', 收入额: 1200 }],
  }

  it('窗口缩放时重绘', () => {
    render(<ChartView spec={spec} />)
    mocks.resize.mockClear()

    fireEvent(window, new Event('resize'))
    expect(mocks.resize).toHaveBeenCalledTimes(1)
  })

  it('卸载时销毁实例并摘掉 resize 监听', () => {
    const { unmount } = render(<ChartView spec={spec} />)
    unmount()

    expect(mocks.dispose).toHaveBeenCalledTimes(1)

    mocks.resize.mockClear()
    fireEvent(window, new Event('resize'))
    expect(mocks.resize).not.toHaveBeenCalled()
  })

  it('规格变化时用新 option 重新渲染同一实例', () => {
    const { rerender } = render(<ChartView spec={spec} />)
    expect(mocks.init).toHaveBeenCalledTimes(1)
    expect(mocks.setOption).toHaveBeenCalledTimes(1)

    rerender(
      <ChartView
        spec={{ ...spec, data: [{ name: '上海', 收入额: 10 }] }}
      />,
    )
    expect(mocks.setOption).toHaveBeenCalledTimes(2)
    expect(lastOption().xAxis.data).toEqual(['上海'])
  })
})
