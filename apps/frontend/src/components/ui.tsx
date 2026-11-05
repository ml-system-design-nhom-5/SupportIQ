import photos from '../product-photos.json'
import { useState, type ReactNode, type ButtonHTMLAttributes } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { AlertCircle, ArrowLeft, ArrowUpRight, Box, Check, ChevronRight, Circle, Clock3, Copy, FileText, Loader2, ShieldCheck, Sparkles, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api'
import type { Money } from '../types'

export function Button({children, variant = 'secondary', busy, className = '', ...props}: ButtonHTMLAttributes<HTMLButtonElement> & {variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; busy?: boolean}) {
  return <button className={`button ${variant} ${className}`} aria-busy={busy || undefined} {...props} disabled={props.disabled || busy}>{busy && <Loader2 className="spin" size={15}/>} {children}</button>
}
export function Brand({area = ''}: {area?: string}) {
  return <span className="brand"><svg aria-hidden="true" viewBox="0 0 28 28" width="28" height="28"><path d="M6 5h16v13H12l-6 5V5Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/><path d="M10 10h8M10 14h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg><strong>SupportIQ</strong>{area && <span className="brand-area">{area}</span>}</span>
}

const statuses: Record<string, [string, string, typeof Circle]> = {
  open: ['Open','info',Circle], received: ['Received','info',Clock3], replied: ['Replied','success',Check],
  awaiting_approval: ['Awaiting approval','warning',Clock3], escalated: ['Escalated','warning',ArrowUpRight], closed: ['Closed','success',Check],
  pending: ['Generating draft','info',Loader2], draft_ready: ['Draft ready','ai',Sparkles], abstained: ['AI abstained','warning',AlertCircle],
  escalation_recommended: ['Escalation recommended','warning',ArrowUpRight], unavailable: ['AI unavailable','danger',AlertCircle], llm_unavailable: ['AI unavailable','danger',AlertCircle],
  authority: ['Authority required','warning',ShieldCheck], assisted: ['Assisted','neutral',Sparkles], manual: ['Manual handling','neutral',Circle],
  valid: ['In effect','success',Check], expired: ['Expired','warning',Clock3], conflicting: ['Conflicting','danger',AlertCircle],
  placed: ['Placed','neutral',Circle], processing: ['Processing','info',Clock3], shipped: ['Shipped','info',Box], delivered: ['Delivered','success',Check], cancelled: ['Cancelled','neutral',X],
  not_shipped: ['Not shipped','neutral',Box], in_transit: ['In transit','info',Box], delayed: ['Delayed','warning',Clock3], lost: ['Lost','danger',AlertCircle],
  requested: ['Refund requested','info',Clock3], under_review: ['Refund under review','info',Clock3], approved: ['Refund approved','success',Check], rejected: ['Refund rejected','danger',X], paid: ['Refund paid','success',Check],
  active: ['Active','success',Check], deactivated: ['Deactivated','neutral',Circle], available: ['Available','success',Check],
  staff: ['Staff','neutral',Circle], manager: ['Manager','info',ShieldCheck], admin: ['Admin','neutral',ShieldCheck],
}
export function Status({value}: {value: string}) {
  const [label, tone, Icon] = statuses[value] || [humanize(value), 'neutral', Circle]
  return <span className={`status ${tone}`}><Icon size={12} aria-hidden="true" className={value === 'pending' ? 'spin' : ''}/>{label}</span>
}
export const humanize = (value: string) => value.replaceAll('_',' ').replace(/^./, char => char.toUpperCase())
export function money(value: Money) { return new Intl.NumberFormat('en-US', {style: 'currency', currency: value.currency, maximumFractionDigits: value.currency === 'VND' ? 0 : 2}).format(value.amount_minor / (value.currency === 'VND' ? 1 : 100)) }
export function Time({value}: {value: string}) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  const relative = minutes < 1 ? 'Just now' : minutes < 60 ? `${minutes} min ago` : minutes < 1440 ? `${Math.floor(minutes/60)} h ago` : `${Math.floor(minutes/1440)} days ago`
  const [absolute, setAbsolute] = useState(false)
  return <time dateTime={value} title={new Date(value).toLocaleString()} onClick={() => setAbsolute(!absolute)}>{absolute ? new Date(value).toLocaleString() : relative}</time>
}
export function ErrorNotice({error, retry}: {error: unknown; retry?: () => void}) {
  const [copied, setCopied] = useState(false)
  if (!error) return null
  const problem = error instanceof ApiError ? error : new ApiError(0, error instanceof Error ? error.message : 'Something went wrong. Try again.')
  return <div className="notice danger" role="alert"><AlertCircle size={18}/><div><strong>{problem.status === 404 ? 'Not found' : problem.status === 403 ? 'Permission denied' : 'Unable to complete the request'}</strong><p>{problem.message}</p>{problem.traceId && <Button variant="ghost" onClick={async () => {await navigator.clipboard.writeText(problem.traceId!); setCopied(true)}}><Copy size={13}/>{copied ? 'Copied' : 'Copy trace ID'}</Button>}{retry && <Button onClick={retry}>Try again</Button>}</div></div>
}
export function Loading({label = 'Loading'}: {label?: string}) { return <div className="loading" role="status" aria-label={label}><div className="skeleton short"/><div className="skeleton"/><div className="skeleton"/><span className="sr-only">{label}</span></div> }
export function Empty({title, children}: {title: string; children?: ReactNode}) { return <div className="empty"><FileText size={24}/><h2>{title}</h2>{children && <p>{children}</p>}</div> }
export function Modal({open, onOpenChange, title, description, children, wide = false}: {open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode; wide?: boolean}) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className={`dialog ${wide ? 'wide' : ''}`} aria-describedby={description ? undefined : undefined}><Dialog.Title>{title}</Dialog.Title><Dialog.Description className={description ? '' : 'sr-only'}>{description || title}</Dialog.Description><Dialog.Close className="dialog-close" aria-label="Close dialog"><X size={18}/></Dialog.Close>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>
}
export function Back({to, children}: {to: string; children: ReactNode}) { return <Link className="back-link" to={to}><ArrowLeft size={14}/>{children}</Link> }
export function NeutralProduct({small = false, name}: {small?: boolean; name?: string}) {
 const photo = name ? (photos as Record<string,{src:string}>)[name] : undefined
 return <div className={`product-image ${small ? 'small' : ''}`}>{photo ? <img src={photo.src} alt={name} loading="lazy"/> : <Box size={small ? 22 : 44} strokeWidth={1} aria-label="Product image unavailable"/>}</div>
}
