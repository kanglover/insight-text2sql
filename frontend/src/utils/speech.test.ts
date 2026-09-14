/**
 * 语音工具函数单测。
 *
 * 只测纯函数：这几个函数的输出直接决定「AI 回复被念成什么样」以及
 * 「语音输入失败时用户看到什么」，是这一块里真正值得锁住的行为。
 * 浏览器 API 调用部分（useSpeech.ts）依赖真实音频环境，不做单测，
 * 由 .tools/screenshot-voice.mjs 做运行态冒烟。
 */

import { describe, expect, it } from 'vitest'
import {
  SPEECH_MAX_CHARS,
  describeAsrError,
  normalizeForSpeech,
  pickChineseVoice,
  truncateForSpeech,
} from './speech'

describe('normalizeForSpeech', () => {
  it('整段丢弃代码块（SQL 逐字念没有意义）', () => {
    const text = '结论如下：\n```sql\nSELECT * FROM dw_fact_revenue\n```\n以上。'
    const out = normalizeForSpeech(text)
    expect(out).not.toContain('SELECT')
    expect(out).toContain('结论如下')
    expect(out).toContain('以上')
  })

  it('行内代码保留文字、去掉反引号', () => {
    expect(normalizeForSpeech('字段 `revenue` 的含义')).toBe('字段 revenue 的含义')
  })

  it('去掉标题与列表符号', () => {
    const out = normalizeForSpeech('## 分析结论\n- 通用计算占比最高\n1. 其次')
    expect(out).not.toMatch(/[#*]/)
    expect(out).toContain('分析结论')
    expect(out).toContain('通用计算占比最高')
  })

  it('拆掉强调标记但保留内容', () => {
    expect(normalizeForSpeech('**通用计算**占比最高')).toBe('通用计算占比最高')
  })

  it('链接只保留可读文字', () => {
    expect(normalizeForSpeech('详见[报表](https://example.com/a)')).toBe('详见报表')
  })

  it('表格竖线转成停顿，分隔行被移除', () => {
    const out = normalizeForSpeech('| 单元 | 收入 |\n| --- | --- |\n| 北京 | 100 |')
    expect(out).not.toContain('|')
    expect(out).toContain('北京')
    expect(out).toContain('，')
  })

  it('折叠多余空白并去掉首尾空白', () => {
    expect(normalizeForSpeech('  收入   同比  增长  ')).toBe('收入 同比 增长')
  })

  it('空输入返回空串', () => {
    expect(normalizeForSpeech('')).toBe('')
  })
})

describe('pickChineseVoice', () => {
  it('没有可用音色时返回 null，交给浏览器默认音色', () => {
    expect(pickChineseVoice([])).toBeNull()
  })

  it('只有非中文音色时返回 null', () => {
    expect(pickChineseVoice([{ lang: 'en-US', name: 'Samantha' }])).toBeNull()
  })

  it('优先普通话而不是其他中文变体', () => {
    const voices = [
      { lang: 'zh-TW', name: 'Meijia' },
      { lang: 'zh-CN', name: 'Tingting' },
    ]
    expect(pickChineseVoice(voices)?.lang).toBe('zh-CN')
  })

  it('普通话里优先常见的高质量音色', () => {
    const voices = [
      { lang: 'zh-CN', name: 'Generic Voice' },
      { lang: 'zh-CN', name: 'Microsoft Xiaoxiao' },
    ]
    expect(pickChineseVoice(voices)?.name).toBe('Microsoft Xiaoxiao')
  })

  it('没有高音质音色时退回任意普通话音色', () => {
    const voices = [{ lang: 'zh-CN', name: 'Generic Voice' }]
    expect(pickChineseVoice(voices)?.name).toBe('Generic Voice')
  })
})

describe('truncateForSpeech', () => {
  it('短文本原样返回', () => {
    expect(truncateForSpeech('短句。')).toBe('短句。')
  })

  it('超长文本在句末标点处截断', () => {
    const text = '第一句话。'.repeat(200) // 1000 字，超过 900
    const out = truncateForSpeech(text)
    expect(out.length).toBeLessThanOrEqual(SPEECH_MAX_CHARS)
    expect(out.endsWith('。')).toBe(true)
  })

  it('句末标点位置太靠前时退化为硬截断，避免丢内容', () => {
    const text = '开头。' + '啊'.repeat(SPEECH_MAX_CHARS)
    const out = truncateForSpeech(text)
    expect(out.length).toBe(SPEECH_MAX_CHARS)
  })

  it('支持自定义上限', () => {
    expect(truncateForSpeech('一二三四五', 3)).toBe('一二三')
  })
})

describe('describeAsrError', () => {
  it('权限被拒时提示去放开麦克风', () => {
    expect(describeAsrError('not-allowed')).toContain('权限')
    expect(describeAsrError('service-not-allowed')).toContain('权限')
  })

  it('没听到声音时提示重说', () => {
    expect(describeAsrError('no-speech')).toContain('再说一次')
  })

  it('没有设备时提示缺麦克风', () => {
    expect(describeAsrError('audio-capture')).toContain('麦克风')
  })

  it('未知错误码也要带上原始码，便于排查', () => {
    expect(describeAsrError('weird-code')).toContain('weird-code')
  })
})
