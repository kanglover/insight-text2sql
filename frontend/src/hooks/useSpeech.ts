/**
 * 语音能力的 React 封装。
 *
 * - useTts：浏览器原生 speechSynthesis，把 AI 回复念出来，同一时刻只播一条；
 * - useAsr：Chrome / Edge 的 webkitSpeechRecognition 语音输入，支持边说边出字。
 *
 * 设计取舍：
 * 1. 两个 hook 在不支持的环境里把 supported 置为 false，由调用方决定隐藏按钮，
 *    而不是弹窗报错 —— 能力缺失不该打断正常使用。
 * 2. 语音识别必须由用户手势触发（浏览器策略），所以只暴露 toggle，不做自动开启。
 * 3. 播报与识别的实例都放 ref 里，避免每次 render 重建导致状态错乱。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { describeAsrError, normalizeForSpeech, pickChineseVoice, truncateForSpeech } from '../utils/speech'

export interface TtsApi {
  /** 当前浏览器是否支持语音播报。 */
  supported: boolean
  /** 正在播报的消息 id，未播报时为 null。 */
  speakingId: string | null
  /** 播报指定消息；对同一条再点一次即停止。 */
  speak: (id: string, text: string) => void
  stop: () => void
}

export function useTts(): TtsApi {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window
  const [speakingId, setSpeakingId] = useState<string | null>(null)
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null)

  const stop = useCallback(() => {
    if (!supported) return
    // cancel 会同步触发 onend，这里先把 ref 清掉避免回调里再 setState 一次
    utterRef.current = null
    window.speechSynthesis.cancel()
    setSpeakingId(null)
  }, [supported])

  const speak = useCallback(
    (id: string, text: string) => {
      if (!supported) return
      // 再点一次 = 停止，和播放器按钮的直觉一致
      if (speakingId === id) {
        stop()
        return
      }

      window.speechSynthesis.cancel()

      const content = truncateForSpeech(normalizeForSpeech(text))
      if (!content) return

      const utter = new SpeechSynthesisUtterance(content)
      utter.lang = 'zh-CN'
      utter.rate = 1
      utter.pitch = 1
      // 音色列表在部分浏览器里是异步填充的，首次可能拿不到，拿不到就用默认
      const voice = pickChineseVoice(window.speechSynthesis.getVoices())
      if (voice) utter.voice = voice

      const settle = () => {
        utterRef.current = null
        setSpeakingId(null)
      }
      utter.onend = settle
      utter.onerror = settle

      utterRef.current = utter
      setSpeakingId(id)
      window.speechSynthesis.speak(utter)
    },
    [supported, speakingId, stop],
  )

  // 切页 / 卸载时闭嘴，否则离开页面后还在念
  useEffect(() => {
    if (!supported) return undefined
    return () => {
      window.speechSynthesis.cancel()
    }
  }, [supported])

  return { supported, speakingId, speak, stop }
}

export interface AsrApi {
  supported: boolean
  listening: boolean
  toggle: () => void
  stop: () => void
}

interface UseAsrOptions {
  /** 识别到最终结果时回调，用于写入输入框。 */
  onFinal: (text: string) => void
  /** 识别过程中的中间结果，用于实时预览。 */
  onInterim?: (text: string) => void
  onError?: (message: string) => void
}

export function useAsr({ onFinal, onInterim, onError }: UseAsrOptions): AsrApi {
  const Ctor =
    typeof window !== 'undefined'
      ? (window.SpeechRecognition ?? window.webkitSpeechRecognition)
      : undefined
  const supported = Boolean(Ctor)

  const [listening, setListening] = useState(false)
  const recRef = useRef<SpeechRecognition | null>(null)
  // 回调放 ref：识别实例只建一次，但每次 render 都要拿到最新的 setState
  const cbRef = useRef({ onFinal, onInterim, onError })
  cbRef.current = { onFinal, onInterim, onError }

  const stop = useCallback(() => {
    const rec = recRef.current
    recRef.current = null
    setListening(false)
    try {
      rec?.stop()
    } catch {
      // 已经结束了，忽略
    }
  }, [])

  const start = useCallback(() => {
    if (!Ctor) {
      cbRef.current.onError?.('当前浏览器不支持语音输入，建议使用 Chrome 或 Edge')
      return
    }
    if (recRef.current) return // 正在听，别重复开

    const rec = new Ctor()
    rec.lang = 'zh-CN'
    // 单次输入：用户说完自然停，避免静默后一直占用麦克风
    rec.continuous = false
    rec.interimResults = true
    rec.maxAlternatives = 1

    rec.onstart = () => setListening(true)

    rec.onresult = (event) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const transcript = result[0]?.transcript ?? ''
        if (result.isFinal) finalText += transcript
        else interimText += transcript
      }
      if (interimText) cbRef.current.onInterim?.(interimText)
      if (finalText) cbRef.current.onFinal(finalText.trim())
    }

    const reset = () => {
      recRef.current = null
      setListening(false)
    }

    rec.onerror = (event) => {
      reset()
      cbRef.current.onError?.(describeAsrError(event.error))
    }
    rec.onend = reset

    recRef.current = rec
    try {
      rec.start()
    } catch {
      // 上一次还没完全释放时 start 会抛，忽略即可
      reset()
    }
  }, [Ctor])

  const toggle = useCallback(() => {
    if (listening) stop()
    else start()
  }, [listening, start, stop])

  useEffect(
    () => () => {
      recRef.current?.abort()
      recRef.current = null
    },
    [],
  )

  return { supported, listening, toggle, stop }
}
