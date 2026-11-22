import { SupportHome, SupportRequest } from './support'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, ArrowUpRight, Check, MessageSquare, Package, Send, Truck } from 'lucide-react'
import { api, post } from '../api'
import { Back, Button, Empty, ErrorNotice, Loading, Modal, NeutralProduct, Status, Time, money } from '../components/ui'
import type { Order, Page, Product, ShopTicket } from '../types'

function usePages<T>(path: string) {
  return useInfiniteQuery({queryKey: [path], initialPageParam: null as string | null,
    queryFn: ({pageParam}) => api<Page<T>>(path + (path.includes('?') ? '&' : '?') + 'limit=12' + (pageParam ? '&cursor=' + encodeURIComponent(pageParam) : '')),
    getNextPageParam: last => last.next_cursor})
}
function More({hasMore, busy, load, label = 'Show more'}: {hasMore: boolean; busy: boolean; load: () => void; label?: string}) { return hasMore && <div className="load-more"><Button busy={busy} onClick={load}>{label}</Button></div> }

function Products() {
  const query = usePages<Product>('/v1/shop/products')
  return <><div className="page-heading"><div><h1>Products</h1><p>Explore the catalog. Your orders and support are a click away.</p></div><Link to="/shop/orders" className="text-link">My orders <ArrowUpRight size={15}/></Link></div>{query.isPending ? <Loading label="Loading products"/> : query.isError && !query.data ? <ErrorNotice error={query.error} retry={() => query.refetch()}/> : <><div className="product-grid">{query.data.pages.flatMap(page => page.items).map(product => <Link className="product-card" key={product.product_id} to={`/shop/products/${product.product_id}`}><NeutralProduct name={product.name}/><div><p className="muted small">{product.category}</p><h2>{product.name}</h2><p className="product-price">{money(product.price)}</p></div></Link>)}</div>{query.data.pages[0].items.length === 0 && <Empty title="No products to show."/>}<More hasMore={!!query.hasNextPage} busy={query.isFetchingNextPage} load={() => query.fetchNextPage()} label="Show more products"/>{query.isFetchNextPageError && <ErrorNotice error={query.error}/>}</>}</>
}
function ProductDetail() {
  const {productId} = useParams()
  const navigate = useNavigate()
  const [buyError,setBuyError] = useState<unknown>(), [checking,setChecking] = useState(false)
  const buyKey = useRef<string | null>(null)
  const client = useQueryClient()
  async function buy() {
    setChecking(true); setBuyError(undefined)
    try { const profile = await api<{phone:string;address:string}>('/v1/profile'); if (!profile.phone?.trim() || !profile.address?.trim()) navigate('/profile', {state:{requireContact:true}}); else {buyKey.current ||= crypto.randomUUID(); const order = await post<Order>('/v1/shop/orders', {product_id:productId}, buyKey.current); buyKey.current = null; await client.invalidateQueries({queryKey:['/v1/shop/orders']}); navigate(`/shop/orders/${order.order_id}`)} } catch(error) {setBuyError(error)} finally {setChecking(false)}
  }
  const query = useQuery({queryKey: ['product',productId], queryFn: () => api<Product>(`/v1/shop/products/${productId}`)})
  if (query.isPending) return <Loading label="Loading product"/>
  if (query.isError) return <ErrorNotice error={query.error} retry={() => query.refetch()}/>
  const product = query.data
  return <><Back to="/shop">Products</Back><div className="product-detail"><NeutralProduct name={product.name}/><div><h1>{product.name}</h1><p className="muted">{product.category}</p><p className="detail-price">{money(product.price)}</p><p>{product.description}</p><Button busy={checking} onClick={buy}>Buy<ArrowRight size={16}/></Button><ErrorNotice error={buyError}/></div></div></>
}

function OrderRow({order}: {order: Order}) {
  return <Link to={`/shop/orders/${order.order_id}`} className="order-row"><NeutralProduct small name={order.lines[0]?.product_name}/><div className="order-row-info"><div className="inline"><strong className="identifier">{order.order_id}</strong><Status value={order.order_status}/></div><p>{order.lines.map(line => line.product_name + (line.quantity > 1 ? ` × ${line.quantity}` : '')).join(', ')}</p><div className="inline muted small"><span><Truck size={13}/>{order.shipment.shipment_status.replaceAll('_',' ')}</span>{order.refund && <Status value={order.refund.refund_status}/>}<span>{new Date(order.placed_at).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'})}</span></div></div><div className="order-row-total"><strong>{money(order.order_total)}</strong><ArrowRight size={16}/></div></Link>
}
function Orders() {
  const query = usePages<Order>('/v1/shop/orders')
  return <><div className="page-heading"><div><h1>My orders</h1><p>Order details, delivery updates, and support in one place.</p></div></div>{query.isPending ? <Loading label="Loading orders"/> : query.isError && !query.data ? <ErrorNotice error={query.error} retry={() => query.refetch()}/> : <><div className="orders-list">{query.data.pages.flatMap(page => page.items).map(order => <OrderRow order={order} key={order.order_id}/>)}</div>{!query.data.pages[0].items.length && <Empty title="You have no orders yet."/>}<More hasMore={!!query.hasNextPage} busy={query.isFetchingNextPage} load={() => query.fetchNextPage()}/>{query.isFetchNextPageError && <ErrorNotice error={query.error}/>}</>}</>
}

export function TicketThread({ticket}: {ticket: ShopTicket}) {
  return <article className="ticket-thread" id={ticket.ticket_id}><div className="thread-heading"><span className="identifier">{ticket.ticket_id}</span><Status value={ticket.customer_status}/><Time value={ticket.created_at}/></div><div className="customer-bubble"><span className="message-author">You</span><p className="plain-text">{ticket.message}</p></div>{ticket.reply ? <div className="support-bubble"><span className="message-author">Reply from support</span><p className="plain-text">{ticket.reply.body}</p><Time value={ticket.reply.sent_at}/></div> : <p className="awaiting-message"><ClockIcon/>No reply yet. A person from our support team replies here.</p>}</article>
}
function ClockIcon() { return <MessageSquare size={15} aria-hidden="true"/> }

function OrderDetail() {
  const {orderId} = useParams(), client = useQueryClient()
  const query = useQuery({queryKey: ['order',orderId], queryFn: () => api<Order>(`/v1/shop/orders/${orderId}`)})
  const [confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>()
  const key=useRef<string|null>(null)
  async function cancel(){setBusy(true);setError(undefined);key.current ||= crypto.randomUUID();try{await post(`/v1/shop/orders/${orderId}/cancellations`,{},key.current);key.current=null;setConfirm(false);await query.refetch();await client.invalidateQueries({queryKey:['/v1/shop/orders']})}catch(error){setError(error)}finally{setBusy(false)}}
  if (query.isPending) return <Loading label="Loading order"/>
  if (query.isError) return <><Back to="/shop/orders">My orders</Back><ErrorNotice error={query.error} retry={() => query.refetch()}/></>
  const order = query.data
  return <><Back to="/shop/orders">My orders</Back><div className="page-heading order-heading"><div><h1>Order <span className="identifier">{order.order_id}</span></h1><p>Placed {new Date(order.placed_at).toLocaleDateString('en-US',{year:'numeric', month:'long', day:'numeric'})}</p></div>{order.order_status === "placed" && <Button variant="danger" onClick={() => setConfirm(true)}>Cancel order</Button>}</div><section className="order-overview"><div className="order-status-grid"><div><h2>Order</h2><Status value={order.order_status}/></div><div><h2>Delivery</h2><Status value={order.shipment.shipment_status}/>{order.shipment.estimated_delivery_text && <p>{order.shipment.estimated_delivery_text}</p>}</div><div><h2>Refund</h2>{order.refund ? <><Status value={order.refund.refund_status}/><p>{money(order.refund.refund_amount)}</p>{order.refund.expected_refund_time && <p>{order.refund.expected_refund_time}</p>}</> : <p className="muted">Not requested</p>}</div></div>{order.shipment.carrier && <div className="delivery-detail"><Truck size={17}/><span>{order.shipment.carrier}</span>{order.shipment.tracking_code && <span className="identifier">{order.shipment.tracking_code}</span>}</div>}<div className="order-lines">{order.lines.map(line => <Link to={`/shop/products/${line.product_id}`} key={line.product_id}><NeutralProduct small name={line.product_name}/><span>{line.product_name}</span><span className="muted">Qty {line.quantity}</span><ArrowUpRight size={15}/></Link>)}</div><div className="order-total"><span>Order total <small>Shipping included: {money(order.shipping_cost)}</small></span><strong>{money(order.order_total)}</strong></div></section><Link className="text-link" to={`/shop/support?order_id=${encodeURIComponent(order.order_id)}`}>Contact support<ArrowRight size={16}/></Link><ErrorNotice error={error}/><Modal open={confirm} onOpenChange={value=>!busy&&setConfirm(value)} title="Cancel this order?" description="This changes the order status to Cancelled."><div className="dialog-actions"><Button disabled={busy} onClick={()=>setConfirm(false)}>Keep order</Button><Button variant="danger" busy={busy} onClick={cancel}>Cancel order</Button></div><ErrorNotice error={error}/></Modal></>
}
function SupportList() {
  const query = usePages<ShopTicket>('/v1/shop/tickets')
  return <><div className="page-heading"><div><h1>Support</h1><p>Your requests and replies from our support team.</p></div><Link className="text-link" to="/shop/orders">Open an order to get help<ArrowRight size={15}/></Link></div>{query.isPending ? <Loading label="Loading support requests"/> : query.isError && !query.data ? <ErrorNotice error={query.error} retry={() => query.refetch()}/> : <>{query.data.pages.flatMap(page => page.items).map(ticket => <Link className="support-row" key={ticket.ticket_id} to={`/shop/support/${ticket.ticket_id}`}><MessageSquare size={20}/><div><strong>{ticket.message}</strong><div className="inline muted small"><span className="identifier">{ticket.ticket_id}</span><span>{ticket.order_id || "General support"}</span><Time value={ticket.created_at}/></div></div><Status value={ticket.customer_status}/><ArrowRight size={16}/></Link>)}{!query.data.pages[0].items.length && <Empty title="You have not written to support yet.">Open an order from My orders to send a message.</Empty>}<More hasMore={!!query.hasNextPage} busy={query.isFetchingNextPage} load={() => query.fetchNextPage()}/></>}</>
}
export function Shop() { return <Routes><Route index element={<Products/>}/><Route path="products/:productId" element={<ProductDetail/>}/><Route path="orders" element={<Orders/>}/><Route path="orders/:orderId" element={<OrderDetail/>}/><Route path="support" element={<SupportHome/>}/><Route path="support/requests" element={<SupportList/>}/><Route path="support/:ticketId" element={<SupportRequest/>}/><Route path="*" element={<Empty title="Page not found"/>}/></Routes> }
