import { useEffect, type ReactNode } from 'react'
import { Icon } from './Icon'

interface ModalProps {
  open: boolean
  title: string
  subtitle?: string
  wide?: boolean
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
}

/** 通用弹窗：遮罩点击与 Esc 都可以关闭。 */
export function Modal({ open, title, subtitle, wide, children, footer, onClose }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className={wide ? 'modal wide' : 'modal'}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <div>
            <h3>{title}</h3>
            {subtitle ? <div className="sub">{subtitle}</div> : null}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="关闭">
            <Icon name="close" size={16} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  )
}
