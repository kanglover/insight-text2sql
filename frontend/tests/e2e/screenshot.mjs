/**
 * 前端 UI 冒烟截图 + 验收脚本（开发期 / CI 用，可提交到 git）。
 *
 * 作用：用无头 Chromium 自动走一遍核心流程并截图，同时做关键断言：
 *   - 问数答案非空
 *   - 数据可视化模块已渲染图表（canvas 有实际尺寸）
 * 任意断言失败，或页面出现 console.error / pageerror，均以非零码退出。
 *
 * 用法：node tests/e2e/screenshot.mjs [baseUrl]
 * 前置：先 make frontend 起服务；Playwright 浏览器见 make smoke-setup。
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
page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`) })
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))

const shot = async (name) => {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false })
  console.log(`saved ${name}.png`)
}

try {
  // 1) 欢迎页
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.qa-welcome h1', { timeout: 15000 })
  await page.waitForTimeout(600)
  await shot('01-welcome')

  // 2) 问数：输入 -> 发送 -> 等待结论
  await page.fill('.qa-input-box textarea', '2026年各经营单元的收入和完成率')
  await page.click('.send-btn')
  await page.waitForSelector('.qa-ai-module', { timeout: 20000 })
  await page.waitForTimeout(400)
  await shot('02-streaming')

  await page.waitForSelector('.qa-answer', { timeout: 120000 })
  await page.waitForTimeout(1200)
  await shot('03-answer')

  // 断言：答案非空
  const answerText = (await page.locator('.qa-answer').first().innerText()).trim()
  assert(answerText.length > 0, '问数答案内容非空')

  // 3) 展开分析过程 + SQL
  const bars = page.locator('.aa-summary-bar')
  if (await bars.count()) { await bars.first().click(); await page.waitForTimeout(300) }
  const sqlTitles = page.locator('.qa-ai-module .mod-title', { hasText: '生成的 SQL' })
  if (await sqlTitles.count()) { await sqlTitles.first().click(); await page.waitForTimeout(300) }
  await shot('04-details')

  // 断言：数据可视化模块已渲染图表
  const chartMod = page.locator('.qa-ai-module', { has: page.locator('.mod-title', { hasText: '数据可视化' }) })
  if (await chartMod.count()) {
    const canvas = chartMod.first().locator('canvas')
    if (await canvas.count()) {
      const box = await canvas.first().boundingBox()
      assert(Boolean(box && box.width > 0 && box.height > 0), '数据可视化模块已渲染图表（canvas 有尺寸）')
    } else {
      assert(false, '数据可视化模块已渲染图表（canvas 存在）')
    }
  } else {
    assert(false, '存在数据可视化模块')
  }

  await page.evaluate(() => document.querySelector('.qa-chat')?.scrollTo(0, 99999))
  await page.waitForTimeout(500)
  await shot('05-bottom')

  // 4) 其余页面
  for (const [name, route, sel] of [
    ['06-logs', '/logs', '.data-table'],
    ['07-app-config', '/system/app', '.app-config-grid'],
    ['08-model-config', '/system/model', '.model-config'],
    ['09-feedback', '/feedback/review', '.data-table'],
  ]) {
    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector(sel, { timeout: 15000 })
    await page.waitForTimeout(700)
    await shot(name)
  }
} catch (e) {
  failures.push(`脚本执行异常: ${e.message}`)
  console.error(e)
} finally {
  await browser.close()
}

const ok = failures.length === 0 && problems.length === 0
if (problems.length) console.log(`\n控制台/页面错误:\n${problems.join('\n')}`)
console.log(ok
  ? '\n✅ 冒烟验收通过'
  : `\n❌ 冒烟验收失败（断言 ${failures.length} 项，控制台错误 ${problems.length} 项）`)
process.exit(ok ? 0 : 1)
