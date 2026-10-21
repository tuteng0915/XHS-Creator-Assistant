import { useId, useState, type ReactNode } from 'react'
import './InfoHint.css'
import './DisabledControlHint.css'

/** Disabled native controls cannot receive focus/pointer events reliably. */
export function DisabledControlHint({ reason, label, children }: {
  reason?: string
  label: string
  children: ReactNode
}) {
  const id = useId()
  const [visible, setVisible] = useState(false)
  const open = Boolean(reason && visible)
  return <span
    className="disabled-control-hint"
    data-disabled={reason ? true : undefined}
    role={reason ? 'group' : undefined}
    aria-label={reason ? label : undefined}
    aria-describedby={open ? id : undefined}
    tabIndex={reason ? 0 : undefined}
    onMouseEnter={() => setVisible(Boolean(reason))}
    onMouseLeave={(event) => {
      if (document.activeElement !== event.currentTarget) setVisible(false)
    }}
    onFocus={() => setVisible(Boolean(reason))}
    onBlur={() => setVisible(false)}
    onClick={() => setVisible(Boolean(reason))}
    onKeyDown={(event) => {
      if (event.key === 'Escape') setVisible(false)
    }}
  >
    {children}
    {open && <span id={id} role="tooltip" className="info-hint-tooltip disabled-control-tooltip">{reason}</span>}
  </span>
}
