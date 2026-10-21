import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react'
import { DisabledControlHint } from './DisabledControlHint'

export function CreatorDialog({ title, onClose, children, wide = false, returnFocusRef, className = '', scrollBody = false, footer, closeDisabledReason }: {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
  className?: string
  scrollBody?: boolean
  footer?: ReactNode
  closeDisabledReason?: string
  returnFocusRef?: RefObject<HTMLElement | null>
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const statusId = useId()
  const close = () => { if (!closeDisabledReason) onClose() }
  useEffect(() => {
    const dialog = ref.current
    const previous = returnFocusRef?.current || document.activeElement as HTMLElement | null
    if (dialog?.showModal) dialog.showModal()
    else dialog?.setAttribute('open', '')
    return () => {
      dialog?.close?.()
      previous?.focus()
    }
  }, [returnFocusRef])
  return (
    <dialog ref={ref} className={`creator-dialog${wide ? ' creator-dialog-wide' : ''}${scrollBody ? ' creator-dialog-scroll' : ''}${className ? ` ${className}` : ''}`} aria-label={title}
      aria-describedby={closeDisabledReason ? statusId : undefined}
      aria-busy={closeDisabledReason ? true : undefined}
      onCancel={(event) => { event.preventDefault(); close() }}>
      <div className="creator-dialog-head">
        <div><h2>{title}</h2>{closeDisabledReason && <p id={statusId} role="status" className="creator-dialog-close-status">{closeDisabledReason}</p>}</div>
        <DisabledControlHint reason={closeDisabledReason} label="关闭暂不可用">
          <button type="button" className="icon-button" disabled={Boolean(closeDisabledReason)} onClick={close} aria-label="关闭">×</button>
        </DisabledControlHint>
      </div>
      {scrollBody ? <div className="creator-dialog-body">{children}</div> : children}
      {footer && <div className="creator-dialog-footer">{footer}</div>}
    </dialog>
  )
}
