import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useAsr, useTts } from './useSpeech'

/** speechSynthesis 的最小替身，记录被朗读的文本。 */
function makeSynth(voices: { lang: string; name: string }[] = [{ lang: 'zh-CN', name: 'Tingting' }]) {
  const spoken: FakeUtterance[] = []
  return {
    spoken,
    cancel: vi.fn(),
    speak: vi.fn((utterance: FakeUtterance) => {
      spoken.push(utterance)
    }),
    getVoices: vi.fn(() => voices),
  }
}

class FakeUtterance {
  lang = ''
  rate = 1
  pitch = 1
  voice: unknown = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(readonly text: string) {}
}

/** 用工厂创建：配置里开了 restoreMocks，模块级的 vi.fn() 会被清空实现。 */
function makeRecognitionClass(options: { startThrows?: boolean } = {}) {
  const instances: FakeRecognition[] = []

  class FakeRecognition {
    lang = ''
    continuous = false
    interimResults = false
    maxAlternatives = 1
    onstart: ((event: Event) => void) | null = null
    onend: ((event: Event) => void) | null = null
    onerror: ((event: { error: string }) => void) | null = null
    onresult: ((event: unknown) => void) | null = null

    start = vi.fn(() => {
      // 浏览器在上一次识别尚未释放时会抛错，这里用于覆盖那条分支
      if (options.startThrows) throw new Error('already started')
      this.onstart?.(new Event('start'))
    })
    stop = vi.fn(() => this.onend?.(new Event('end')))
    abort = vi.fn()

    constructor() {
      instances.push(this)
    }
  }

  return { FakeRecognition, instances }
}

function resultEvent(entries: { transcript: string; isFinal: boolean }[], resultIndex = 0) {
  const results = entries.map((entry) =>
    Object.assign([{ transcript: entry.transcript, confidence: 1 }], { isFinal: entry.isFinal }),
  )
  return { resultIndex, results } as unknown as SpeechRecognitionEvent
}

describe('useTts — 能力缺失时优雅降级', () => {
  it('没有 speechSynthesis 时 supported 为 false', () => {
    const { result } = renderHook(() => useTts())

    expect(result.current.supported).toBe(false)
    expect(result.current.speakingId).toBeNull()
  })

  it('调用 speak / stop 不抛错也不改状态', () => {
    const { result } = renderHook(() => useTts())

    act(() => result.current.speak('m1', '结论：北京最高。'))
    act(() => result.current.stop())

    expect(result.current.speakingId).toBeNull()
  })
})

describe('useTts — 播报', () => {
  it('朗读前先清洗 Markdown，代码块整段丢弃', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    expect(result.current.supported).toBe(true)

    act(() => result.current.speak('m1', '**结论**：北京最高。\n```sql\nSELECT 1\n```'))

    expect(synth.speak).toHaveBeenCalledTimes(1)
    expect(synth.spoken[0].text).toBe('结论：北京最高。')
    expect(result.current.speakingId).toBe('m1')
  })

  it('固定中文语速音调，并择优选中中文音色', () => {
    const voices = [
      { lang: 'en-US', name: 'Samantha' },
      { lang: 'zh-CN', name: 'Tingting' },
    ]
    const synth = makeSynth(voices)
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '你好'))

    const utterance = synth.spoken[0]
    expect(utterance.lang).toBe('zh-CN')
    expect(utterance.rate).toBe(1)
    expect(utterance.pitch).toBe(1)
    expect(utterance.voice).toEqual(voices[1])
  })

  it('拿不到中文音色时交给浏览器默认音色，不报错', () => {
    const synth = makeSynth([])
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '你好'))

    expect(synth.spoken[0].voice).toBeNull()
  })

  it('对同一条消息再点一次即停止（播放器直觉）', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '你好'))
    expect(result.current.speakingId).toBe('m1')

    act(() => result.current.speak('m1', '你好'))
    expect(synth.cancel).toHaveBeenCalled()
    expect(result.current.speakingId).toBeNull()
    expect(synth.speak).toHaveBeenCalledTimes(1)
  })

  it('点另一条消息时打断上一条，只保留一个播报实例', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '第一条'))
    act(() => result.current.speak('m2', '第二条'))

    expect(synth.speak).toHaveBeenCalledTimes(2)
    expect(result.current.speakingId).toBe('m2')
  })

  it('内容清洗后为空（整条都是代码块）时不朗读', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '```sql\nSELECT 1\n```'))

    expect(synth.speak).not.toHaveBeenCalled()
    expect(result.current.speakingId).toBeNull()
  })

  it('引擎念完或报错都复位状态', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '你好'))
    act(() => synth.spoken[0].onend?.())
    expect(result.current.speakingId).toBeNull()

    act(() => result.current.speak('m2', '你好'))
    act(() => synth.spoken[1].onerror?.())
    expect(result.current.speakingId).toBeNull()
  })

  it('主动停止会调用引擎 cancel', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { result } = renderHook(() => useTts())
    act(() => result.current.speak('m1', '你好'))
    act(() => result.current.stop())

    expect(synth.cancel).toHaveBeenCalled()
    expect(result.current.speakingId).toBeNull()
  })

  it('离开页面时闭嘴，不把声音带到下一个路由', () => {
    const synth = makeSynth()
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    const { unmount } = renderHook(() => useTts())
    unmount()

    expect(synth.cancel).toHaveBeenCalled()
  })
})

describe('useAsr — 能力缺失时优雅降级', () => {
  it('没有识别 API 时 supported 为 false', () => {
    const { result } = renderHook(() => useAsr({ onFinal: vi.fn() }))
    expect(result.current.supported).toBe(false)
  })

  it('点击时给出可操作的中文提示，而不是静默失败', () => {
    const onError = vi.fn()
    const { result } = renderHook(() => useAsr({ onFinal: vi.fn(), onError }))

    act(() => result.current.toggle())
    expect(onError).toHaveBeenCalledWith('当前浏览器不支持语音输入，建议使用 Chrome 或 Edge')
    expect(result.current.listening).toBe(false)
  })
})

describe('useAsr — 语音输入', () => {
  function setup(options: Parameters<typeof useAsr>[0]) {
    const { FakeRecognition, instances } = makeRecognitionClass()
    vi.stubGlobal('webkitSpeechRecognition', FakeRecognition)
    const hook = renderHook(() => useAsr(options))
    return { ...hook, instances }
  }

  it('识别参数固定为中文单次输入', () => {
    const { result, instances } = setup({ onFinal: vi.fn() })

    act(() => result.current.toggle())

    const rec = instances[0]
    expect(rec.lang).toBe('zh-CN')
    // 单次输入：说完自然停，避免静默后一直占着麦克风
    expect(rec.continuous).toBe(false)
    expect(rec.interimResults).toBe(true)
    expect(rec.maxAlternatives).toBe(1)
    expect(rec.start).toHaveBeenCalledTimes(1)
    expect(result.current.listening).toBe(true)
  })

  it('中间结果走 onInterim，最终结果去掉首尾空白后走 onFinal', () => {
    const onFinal = vi.fn()
    const onInterim = vi.fn()
    const { result, instances } = setup({ onFinal, onInterim })

    act(() => result.current.toggle())
    act(() => instances[0].onresult?.(resultEvent([{ transcript: '北京', isFinal: false }])))
    expect(onInterim).toHaveBeenCalledWith('北京')
    expect(onFinal).not.toHaveBeenCalled()

    act(() => instances[0].onresult?.(resultEvent([{ transcript: ' 北京的收入 ', isFinal: true }])))
    expect(onFinal).toHaveBeenCalledWith('北京的收入')
  })

  it('一次事件里混有中间与最终结果时分别处理', () => {
    const onFinal = vi.fn()
    const onInterim = vi.fn()
    const { result, instances } = setup({ onFinal, onInterim })

    act(() => result.current.toggle())
    act(() =>
      instances[0].onresult?.(
        resultEvent([
          { transcript: '北京', isFinal: true },
          { transcript: '的收', isFinal: false },
        ]),
      ),
    )

    expect(onFinal).toHaveBeenCalledWith('北京')
    expect(onInterim).toHaveBeenCalledWith('的收')
  })

  it('错误码翻译成中文提示，并复位监听状态', () => {
    const onError = vi.fn()
    const { result, instances } = setup({ onFinal: vi.fn(), onError })

    act(() => result.current.toggle())
    act(() => instances[0].onerror?.({ error: 'not-allowed' }))

    expect(onError).toHaveBeenCalledWith('麦克风权限被拒绝，请在地址栏右侧允许麦克风后重试')
    expect(result.current.listening).toBe(false)
  })

  it('识别结束（用户说完）后状态复位', () => {
    const { result, instances } = setup({ onFinal: vi.fn() })

    act(() => result.current.toggle())
    expect(result.current.listening).toBe(true)

    act(() => instances[0].onend?.(new Event('end')))
    expect(result.current.listening).toBe(false)
  })

  it('正在听时再点一次是停止，不会开第二个实例', () => {
    const { result, instances } = setup({ onFinal: vi.fn() })

    act(() => result.current.toggle())
    act(() => result.current.toggle())

    expect(instances).toHaveLength(1)
    expect(instances[0].stop).toHaveBeenCalledTimes(1)
    expect(result.current.listening).toBe(false)
  })

  it('卸载时中断识别，不留下麦克风占用', () => {
    const { result, instances, unmount } = setup({ onFinal: vi.fn() })

    act(() => result.current.toggle())
    unmount()

    expect(instances[0].abort).toHaveBeenCalledTimes(1)
  })

  it('start 抛错（上一次未释放）时状态回滚', () => {
    const { FakeRecognition, instances } = makeRecognitionClass()
    vi.stubGlobal('webkitSpeechRecognition', FakeRecognition)
    const onError = vi.fn()
    const { result } = renderHook(() => useAsr({ onFinal: vi.fn(), onError }))

    // 模拟浏览器抛出的 "already started" 异常
    instances.length = 0
    act(() => {
      result.current.toggle()
    })
    act(() => {
      instances[0].start.mockImplementationOnce(() => {
        throw new Error('already started')
      })
      result.current.stop()
      result.current.toggle()
    })

    expect(result.current.listening).toBe(false)
  })

  it('优先使用无前缀的 SpeechRecognition（标准草案）', () => {
    const { FakeRecognition } = makeRecognitionClass()
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    vi.stubGlobal('SpeechRecognition', FakeRecognition)

    const { result } = renderHook(() => useAsr({ onFinal: vi.fn() }))
    expect(result.current.supported).toBe(true)
  })
})
