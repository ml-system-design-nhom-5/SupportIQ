import {useRef, useState, type FormEvent} from 'react'
import {Link, useNavigate, useParams, useSearchParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {ArrowRight, MessageSquare, Send} from 'lucide-react'
import {api, post} from '../api'
import {Back, Button, ErrorNotice, Loading} from '../components/ui'
import {TicketThread} from './shop'
import type {ShopTicket} from '../types'



export function SupportHome() {
  const navigate=useNavigate(), input=useRef<HTMLTextAreaElement>(null)
  const [searchParams]=useSearchParams(), orderId=searchParams.get('order_id') || null
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>()
  const attempt=useRef<{message:string;orderId:string|null;key:string}|null>(null)
  async function send(event:FormEvent) {
    event.preventDefault();if(busy||!message.trim()||message.length>2000)return
    setBusy(true);setError(undefined)
    if(attempt.current?.message!==message||attempt.current?.orderId!==orderId)attempt.current={message,orderId,key:crypto.randomUUID()}
    try {const ticket=await post<ShopTicket>('/v1/shop/tickets',{message,order_id:orderId},attempt.current.key);navigate(`/shop/support/${ticket.ticket_id}`)}catch(error){setError(error)}finally{setBusy(false)}
  }
  return <><div className="page-heading"><div><h1>How can we help?</h1><p>Ask a question or get help with a purchase. Our team replies here.</p></div><Link className="text-link" to="/shop/support/requests">Your requests<ArrowRight size={16}/></Link></div><section className="support-section"><div className="section-heading"><MessageSquare size={18}/><h2>Write to our team</h2></div>{orderId && <p className="muted">About order <span className="identifier">{orderId}</span></p>}<form onSubmit={send}><div className="field"><label htmlFor="general-message">Your message</label><textarea ref={input} id="general-message" rows={5} value={message} onChange={event=>setMessage(event.target.value)} aria-describedby="general-help general-count" placeholder="What would you like help with?"/></div><p id="general-help" className="muted small">A person reviews each request and sends one reply. For another question, create a new request.</p><div className="form-bottom"><span id="general-count" className={message.length>2000?'danger-text':'muted'}>{message.length} / 2,000 characters</span><Button type="submit" variant="primary" busy={busy} disabled={!message.trim()||message.length>2000}><Send size={15}/>Send request</Button></div><ErrorNotice error={error}/></form></section></>
}

export function SupportRequest() {
  const {ticketId}=useParams()
  const query=useQuery({queryKey:['support-request',ticketId],queryFn:()=>api<ShopTicket>(`/v1/shop/tickets/${ticketId}`)})
  return <><Back to="/shop/support/requests">Your requests</Back><div className="page-heading"><div><h1>Support request</h1><p>{ticketId} · A reply from our team will appear here.</p></div><Link to="/shop/support" className="text-link">New request<ArrowRight size={15}/></Link></div>{query.isPending?<Loading/>:query.isError?<ErrorNotice error={query.error} retry={()=>query.refetch()}/>:<section className="support-section"><TicketThread ticket={query.data}/><Button onClick={()=>query.refetch()} busy={query.isFetching}>Check for reply</Button></section>}</>
}
