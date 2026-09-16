/**
 * 「数据可视化 / 数据表格」模块专项冒烟脚本（开发期 / CI 用，可提交到 git）。
 * 重点确认图表真的渲染出来（canvas 有尺寸）、表格模块存在。
 * 用法：node tests/e2e/screenshot-chart.mjs [baseUrl]
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.argv[2] ?? 'http://127.0.0.1:5173'
const OUT = '/tmp/insight-shots'
mkdirSync(OUT, { recursive: true })

const failures = []
const assert = (cond, msg) => {
  if (cond) console.log(`  ✓ ${msg}`)
  else { failures.push(msg); console.log(`  ✗ ${msg}`) }
}

const browser = await chromium.launch(
  process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
)
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

const problems = []
page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`))

try {
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.qa-welcome h1', { timeout: 15000 })
  await page.fill('.qa-input-box textarea', '2026年各经营单元的收入和完成率')
  await page.click('.send-btn')
  await page.waitForSelector('.qa-answer', { timeout: 150000 })
  await page.waitForTimeout(2000)

  // 数据可视化模块
  const mod = page.locator('.qa-ai-module', { has: page.locator('.mod-title', { hasText: '数据可视化' }) })
  if (await mod.count()) {
    await mod.first().scrollIntoViewIfNeeded()
    await page.waitForTimeout(800)
    await mod.first().screenshot({ path: `${OUT}/10-chart.png` })
    console.log('saved 10-chart.png')
    const canvas = mod.first().locator('canvas')
    if (await canvas.count()) {
      const box = await canvas.first().boundingBox()
      assert(Boolean(box && box.width > 0 && box.height > 0), '图表 canvas 已渲染（有尺寸）')
    } else {
      assert(false, '图表 canvas 存在')
    }
  } else {
    assert(false, '存在数据可视化模块')
  }

  // 数据表格模块
  const table = page.locator('.qa-ai-module', { has: page.locator('.mod-title', { hasText: '数据表格' }) })
  if (await table.count()) {
    await table.first().scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await table.first().screenshot({ path: `${OUT}/11-table.png` })
    console.log('saved 11-table.png')
    const rows = table.first().locator('tr')
    assert((await rows.count()) > 1, '数据表格模块含表头+数据行')
  } else {
    assert(false, '存在数据表格模块')
  }
} catch (e) {
  failures.push(`脚本执行异常: ${e.message}`)
  console.error(e)
} finally {
  await browser.close()
}

const ok = failures.length === 0 && problems.length === 0
if (problems.length) console.log(`\n页面错误:\n${problems.join('\n')}`)
console.log(ok ? '\n✅ 图表冒烟通过' : `\n❌ 图表冒烟失败（断言 ${failures.length} 项，页面错误 ${problems.length} 项）`)
process.exit(ok ? 0 : 1)
