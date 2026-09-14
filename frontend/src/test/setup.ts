/**
 * vitest 全局前置。
 *
 * jsdom 只实现了浏览器 API 的一个子集，这里补上组件用到的、但 jsdom 没有的几项，
 * 否则会出现「测试环境能力缺失」导致的假失败（而不是代码真的有 bug）。
 */

import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// 不启用 vitest globals，所以手动挂 cleanup，避免用例之间 DOM 互相污染
afterEach(() => {
  cleanup()
})

// jsdom 不实现 ResizeObserver；ChartView 用它监听容器尺寸变化
if (!('ResizeObserver' in globalThis)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Object.defineProperty(globalThis, 'ResizeObserver', {
    writable: true,
    configurable: true,
    value: ResizeObserverStub,
  })
}

// jsdom 不实现 matchMedia；响应式相关的组件会读它
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    }),
  })
}

// jsdom 的 URL.createObjectURL 缺失，日志页导出 CSV 会用到
if (!URL.createObjectURL) {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    configurable: true,
    value: () => 'blob:mock',
  })
}
if (!URL.revokeObjectURL) {
  Object.defineProperty(URL, 'revokeObjectURL', {
    writable: true,
    configurable: true,
    value: () => undefined,
  })
}

// jsdom 没有实现 SpeechSynthesis；useTts 靠 `'speechSynthesis' in window` 判断能力，
// 所以必须把键本身删掉（置为 undefined 仍会命中 in 判断）。需要它的用例自行注入 mock。
if ('speechSynthesis' in window) {
  delete (window as unknown as Record<string, unknown>).speechSynthesis
  delete (globalThis as unknown as Record<string, unknown>).speechSynthesis
}
