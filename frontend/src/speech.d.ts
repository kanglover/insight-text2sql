/**
 * Web Speech API 中「语音识别」部分的类型声明。
 *
 * TypeScript 的 lib.dom 只带了 speechSynthesis（语音播报），没有带
 * SpeechRecognition（语音输入）—— 它至今仍是草案，Chrome / Edge 用
 * webkit 前缀暴露。这里补一份最小声明，避免在业务代码里写 any。
 *
 * 本文件没有 import / export，因此是全局声明，会自动与 lib.dom 合并。
 */

interface SpeechRecognitionAlternative {
  readonly transcript: string
  readonly confidence: number
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string
  readonly message: string
}

interface SpeechRecognition extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onstart: ((event: Event) => void) | null
  onend: ((event: Event) => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  onresult: ((event: SpeechRecognitionEvent) => void) | null
}

interface Window {
  SpeechRecognition?: { new (): SpeechRecognition }
  webkitSpeechRecognition?: { new (): SpeechRecognition }
}
