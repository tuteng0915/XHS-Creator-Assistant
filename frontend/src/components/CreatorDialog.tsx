import { useEffect, useRef, type ReactNode } from 'react'

export function CreatorDialog({ title, onClose, children }: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    const previous = document.activeElement as HTMLElement | null
    if (dialog?.showModal) dialog.showModal()
    else dialog?.setAttribute('open', '')
    return () => {
      dialog?.close?.()
      previous?.focus()
    }
  }, [])
  return (
    <dialog ref={ref} className="creator-dialog" aria-label={title}
      onCancel={(event) => { event.preventDefault(); onClose() }}>
      <div className="creator-dialog-head">
        <h2>{title}</h2>
        <button type="button" onClick={onClose} aria-label="关闭">×</button>
      </div>
      {children}
    </dialog>
  )
}
