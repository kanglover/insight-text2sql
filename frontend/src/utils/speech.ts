/**
 * 语音能力的纯函数部分：播报文本清洗、音色选择、错误码翻译。
 *
 * 这里不碰任何状态与副作用，所以可以直接单测；真正调用浏览器 API 的部分
 * 在 hooks/useSpeech.ts。
 */

/** 单次播报的最大字符数。超长文本一次性交给引擎会明显卡顿。 */
export const SPEECH_MAX_CHARS = 900

/**
 * 把 Markdown 回复清洗成适合朗读的纯文本。
 *
 * 重点是把「看着有用、念出来全噪音」的内容去掉：代码块（SQL 逐字念毫无意义）、
 * 表格竖线、列表符号、强调星号、链接语法。
 */
export function normalizeForSpeech(raw: string): string {
  if (!raw) return ''
  let text = raw

  // 代码块整段丢弃，行内代码保留文字
  text = text.replace(/```[\s\S]*?```/g, ' ')
  text = text.replace(/`([^`]*)`/g, '$1')

  // 标题 / 引用 / 列表符号
  text = text.replace(/^[ \t]*#{1,6}[ \t]*/gm, '')
  text = text.replace(/^[ \t]*[>*+-][ \t]+/gm, '')

  // 强调符号
  text = text.replace(/\*\*([^*]*)\*\*/g, '$1')
  text = text.replace(/\*([^*]*)\*/g, '$1')
  text = text.replace(/__([^_]*)__/g, '$1')

  // 链接只保留可读文字
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')

  // 表格分隔行直接去掉，剩下的竖线读成停顿
  text = text.replace(/^[ \t]*\|?[\s:|-]{4,}\|?[ \t]*$/gm, ' ')
  text = text.replace(/\|/g, '，')

  // 折叠空白
  text = text.replace(/[ \t]+/g, ' ')
  text = text.replace(/\n{2,}/g, '\n')

  return text.trim()
}

/**
 * 从可用音色里挑一个中文音色；挑不到返回 null，让浏览器用默认音色。
 *
 * 浏览器的中文音色列表在各平台差异很大（macOS 有 Tingting，Windows 有
 * Huihui / Xiaoxiao，Chrome 还有自己的在线音色），所以只做「优先普通话」
 * 的偏好排序，不强求命中某个具体名字。
 */
export function pickChineseVoice<T extends { lang: string; name: string }>(
  voices: T[],
): T | null {
  if (!voices.length) return null
  const chinese = voices.filter(
    (voice) => /^zh/i.test(voice.lang) || /zh[-_]?(CN|Hans|SG)/i.test(voice.lang),
  )
  if (!chinese.length) return null

  const mandarin = chinese.filter((voice) => /zh[-_]?CN/i.test(voice.lang))
  const pool = mandarin.length ? mandarin : chinese
  const natural = pool.find((voice) =>
    /(Xiaoxiao|Xiaoyi|Yunxi|Yunyang|Tingting|Huihui|Meijia|Kangkang)/i.test(voice.name),
  )
  return natural ?? pool[0]
}

/** 超长文本按句末标点截断，避免念到一半被硬切。 */
export function truncateForSpeech(text: string, max = SPEECH_MAX_CHARS): string {
  if (text.length <= max) return text
  const head = text.slice(0, max)
  const lastStop = Math.max(
    head.lastIndexOf('。'),
    head.lastIndexOf('！'),
    head.lastIndexOf('？'),
    head.lastIndexOf('；'),
  )
  // 截断点太靠前就不切了，否则会丢掉大段内容
  return lastStop > max * 0.5 ? head.slice(0, lastStop + 1) : head
}

/** 把浏览器的语音识别错误码翻译成能指导用户下一步动作的中文。 */
export function describeAsrError(code: string): string {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return '麦克风权限被拒绝，请在地址栏右侧允许麦克风后重试'
    case 'no-speech':
      return '没有听到声音，请再说一次'
    case 'audio-capture':
      return '没有检测到可用的麦克风设备'
    case 'network':
      return '语音识别服务网络异常，请稍后重试'
    case 'aborted':
      return '语音输入已取消'
    default:
      return `语音识别失败（${code || '未知错误'}）`
  }
}
