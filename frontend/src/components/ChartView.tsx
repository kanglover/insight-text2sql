/**
 * 图表渲染。
 *
 * 规格完全由后端推导（见 `app/text2sql/nodes/interpret.py` 的 `build_chart`），
 * 前端只做「按 type 选组件」。这样同一份结果在问数页、报表页、导出里
 * 能共用同一套图表规则。
 */

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ChartSpec } from '../types'
import { formatNumber } from '../utils/format'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
])

const PALETTE = ['#2f54eb', '#36cfc9', '#f5a623', '#8b5cf6', '#4f6ff5', '#c73a7a']

/** 比率型度量（完成率、占比…）量级和金额/数量差几个数量级，需要单独一根 Y 轴。 */
const RATIO_RE = /率|占比|比例|百分比/

/** 完成率这类指标用虚线 + 圆点表达，和柱状的数量形成视觉区分。 */
const RATIO_COLOR = '#f5a623'

interface ChartViewProps {
  spec: ChartSpec
}

export function ChartView({ spec }: ChartViewProps) {
  if (spec.type === 'metric') {
    return (
      <div className="metric-row">
        {spec.metrics.map((metric) => (
          <div className="metric-box" key={metric.label}>
            <div className="label">{metric.label}</div>
            <div className="value">{formatNumber(metric.value)}</div>
          </div>
        ))}
      </div>
    )
  }
  return <EchartsView spec={spec} />
}

function EchartsView({ spec }: { spec: Exclude<ChartSpec, { type: 'metric' }> }) {
  const holder = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!holder.current) return
    const instance = echarts.init(holder.current, undefined, { renderer: 'canvas' })
    instance.setOption(buildOption(spec), true)

    const resize = () => instance.resize()
    window.addEventListener('resize', resize)
    // 容器尺寸变化（侧栏折叠、窗口缩放）时也要重绘
    const observer = new ResizeObserver(resize)
    observer.observe(holder.current)

    return () => {
      window.removeEventListener('resize', resize)
      observer.disconnect()
      instance.dispose()
    }
  }, [spec])

  return <div className="chart-canvas" style={{ height: chartHeight(spec) }} ref={holder} />
}

/** 类目越多，画布越高，给旋转后的轴标签留出空间。 */
function chartHeight(spec: Exclude<ChartSpec, { type: 'metric' }>): number {
  if (spec.type === 'pie') return 300
  const count = spec.data.length
  if (count > 16) return 420
  if (count > 8) return 360
  return 300
}

function buildOption(spec: Exclude<ChartSpec, { type: 'metric' }>): echarts.EChartsCoreOption {
  const axisStyle = {
    axisLine: { lineStyle: { color: '#e5e7eb' } },
    axisLabel: { color: '#6b7280', fontSize: 12 },
    splitLine: { lineStyle: { color: '#f1f5f9' } },
  }

  if (spec.type === 'pie') {
    return {
      color: PALETTE,
      tooltip: { trigger: 'item', valueFormatter: (value: number) => formatNumber(value) },
      legend: { bottom: 0, icon: 'circle', textStyle: { color: '#4b5563', fontSize: 12 } },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          label: { formatter: '{b}\n{d}%', color: '#4b5563', fontSize: 12 },
          data: spec.data.map((item) => ({ name: String(item.name), value: item.value })),
        },
      ],
    }
  }

  const isLine = spec.type === 'line'
  const count = spec.data.length
  // 类目多的时候旋转并让 echarts 自行抽稀标签，避免文字糊成一片；
  // 精确的名字可以看 tooltip 或下方的数据表格。
  const rotate = count > 16 ? 45 : count > 8 ? 28 : 0

  // 同时存在「金额/数量」和「比率」时拆成双 Y 轴。
  // 否则完成率（40~90）会被收入（上千）压成贴着 X 轴的一条线，等于白画。
  const ratioNames = spec.series.filter((name) => RATIO_RE.test(name))
  const valueNames = spec.series.filter((name) => !RATIO_RE.test(name))
  const dualAxis = ratioNames.length > 0 && valueNames.length > 0

  const ratioIndex = spec.series.findIndex((name) => ratioNames.includes(name))

  // 配色按「非比率序列的顺序」分配，比率序列固定用橙色，保证同一份数据每次渲染颜色一致
  const colors = spec.series.map((name) => {
    if (dualAxis && RATIO_RE.test(name)) return RATIO_COLOR
    const slot = valueNames.indexOf(name)
    return PALETTE[(slot >= 0 ? slot : ratioIndex) % PALETTE.length]
  })

  return {
    color: colors,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: isLine ? 'line' : 'shadow' },
      valueFormatter: (value: number) => formatNumber(value),
    },
    legend: {
      top: 0,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#4b5563', fontSize: 12 },
    },
    grid: { left: 8, right: dualAxis ? 24 : 16, bottom: 4, top: 36, containLabel: true },
    xAxis: {
      type: 'category',
      // 不设 name：类目标签本身已经说明了维度，而 ECharts 会把 name 摆在轴末端，
      // 双 Y 轴时正好和右侧的 "100%" 撞在一起，得不偿失。
      data: spec.data.map((row) => String(row.name ?? '')),
      ...axisStyle,
      axisLabel: {
        ...axisStyle.axisLabel,
        rotate,
        fontSize: count > 16 ? 11 : 12,
        interval: count > 16 ? 'auto' : 0,
      },
      splitLine: { show: false },
    },
    yAxis: dualAxis
      ? [
          { type: 'value', name: '金额 / 数量', nameTextStyle: { color: '#9ca3af', fontSize: 11 }, ...axisStyle },
          {
            type: 'value',
            name: '比率(%)',
            nameTextStyle: { color: '#9ca3af', fontSize: 11 },
            position: 'right',
            axisLine: { lineStyle: { color: '#f5a623' } },
            axisLabel: { color: '#b45309', fontSize: 12, formatter: '{value}%' },
            splitLine: { show: false },
          },
        ]
      : { type: 'value', ...axisStyle },
    series: spec.series.map((name) => {
      const isRatio = dualAxis && RATIO_RE.test(name)
      return {
        name,
        // 双轴时把比率画成折线，既能看清趋势也不会被柱状挡住
        type: isRatio ? 'line' : isLine ? 'line' : 'bar',
        smooth: isRatio || isLine,
        showSymbol: isRatio || (isLine && count <= 20),
        symbolSize: isRatio ? 6 : undefined,
        yAxisIndex: isRatio ? 1 : 0,
        barMaxWidth: 34,
        itemStyle: isRatio ? undefined : isLine ? undefined : { borderRadius: [4, 4, 0, 0] },
        data: spec.data.map((row) => row[name] as number),
      }
    }),
  }
}
