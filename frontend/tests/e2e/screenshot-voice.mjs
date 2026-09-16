/**
 * 语音功能专项冒烟脚本（开发期 / CI 用，可提交到 git）。
 * 探测浏览器语音能力，并断言关键交互元素存在（按钮/开关是否可用取决于浏览器能力，不在此判定）。
 * 用法：node tests/e2e/screenshot-voice.mjs [baseUrl]
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

const mic = 'button[aria-label="语音输入"]'
const speak = 'button:has-text("语音播放"), button:has-text("停止播报")'

try {
  // ---- 浏览器能力探测 ----
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.qa-input-box', { timeout: 15000 })
  await page.waitForTimeout(500)

  const caps = await page.evaluate(() => ({
    speechSynthesis: 'speechSynthesis' in window,
    SpeechRecognition: 'SpeechRecognition' in window,
    webkitSpeechRecognition: 'webkitSpeechRecognition' in window,
    voiceCount: 'speechSynthesis' in window ? window.speechSynthesis.getVoices().length : -1,
  }))
  console.log('浏览器能力:', JSON.stringify(caps))

  // ---- 1. 输入区麦克风按钮 ----
  const micBtn = page.locator(mic)
  const micCount = await micBtn.count()
  assert(micCount > 0, '输入区存在语音输入按钮')
  if (micCount) {
    console.log(`麦克风按钮 disabled: ${await micBtn.first().isDisabled()}`)
    await page.locator('.qa-input-area').screenshot({ path: `${OUT}/v1-input-mic.png` })
    console.log('saved v1-input-mic.png')
  }

  // ---- 2. 打开历史会话，检查 AI 回复的播报按钮 ----
  const firstSession = page.locator('.qa-sb-item').first()
  if (await firstSession.count()) {
    await firstSession.click()
    await page.waitForSelector('.qa-msg-actions', { timeout: 15000 })
    await page.waitForTimeout(500)

    const speakBtn = page.locator(speak)
    const speakCount = await speakBtn.count()
    assert(speakCount > 0, 'AI 回复存在语音播报按钮')

    await page.locator('.qa-msg').first().hover()
    await page.waitForTimeout(400)
    await page.evaluate(() => document.querySelector('.qa-chat')?.scrollTo(0, 99999))
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${OUT}/v2-answer-actions.png` })
    console.log('saved v2-answer-actions.png')

    if (speakCount && !(await speakBtn.first().isDisabled())) {
      await speakBtn.first().click()
      await page.waitForTimeout(900)
      await page.screenshot({ path: `${OUT}/v3-speaking.png` })
      console.log('saved v3-speaking.png')
    }

    if (micCount && !(await micBtn.first().isDisabled())) {
      await micBtn.first().click()
      await page.waitForTimeout(1800)
      const toast = await page.locator('.toast').innerText().catch(() => '')
      console.log(`点击麦克风后的提示: ${toast.trim() || '(无)'}`)
      await page.screenshot({ path: `${OUT}/v4-mic-toast.png` })
      console.log('saved v4-mic-toast.png')
    }
  }

  // ---- 3. 应用配置页的语音开关 ----
  await page.goto(`${BASE}/system/app`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.app-config-grid', { timeout: 15000 })
  await page.waitForTimeout(700)
  const switches = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.app-card')).map((card) => ({
      name: card.querySelector('.app-card-name')?.textContent?.trim(),
      on: card.querySelector('.toggle, [role="switch"], input')?.getAttribute('aria-checked') ?? 'n/a',
    })),
  )
  const voiceSwitches = switches.filter((s) => /语音/.test(s.name ?? ''))
  assert(voiceSwitches.length > 0, '应用配置含语音相关开关')
  console.log('应用配置开关:', JSON.stringify(voiceSwitches))
  await page.screenshot({ path: `${OUT}/v5-app-config.png` })
  console.log('saved v5-app-config.png')
} catch (e) {
  failures.push(`脚本执行异常: ${e.message}`)
  console.error(e)
} finally {
  await browser.close()
}

const ok = failures.length === 0 && problems.length === 0
if (problems.length) console.log(`\n控制台/页面错误:\n${problems.join('\n')}`)
console.log(ok ? '\n✅ 语音冒烟通过' : `\n❌ 语音冒烟失败（断言 ${failures.length} 项，控制台错误 ${problems.length} 项）`)
process.exit(ok ? 0 : 1)
