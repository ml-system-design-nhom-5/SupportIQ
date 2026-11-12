import {useQueryClient} from '@tanstack/react-query'
import {api} from './api'
import type {Session} from './types'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Inbox, LogOut, Shield, UserRound, BarChart3, Users, Layers, ArrowRight, ShoppingBag } from 'lucide-react'
import { ApiError } from './api'
import { Brand, Button, ErrorNotice, Loading, humanize } from './components/ui'
import { roleHome, useSession } from './session'
import { Shop } from './features/shop'
import { Console } from './features/console'
import { Admin } from './features/admin'
import { Reports } from './features/reports'
import type { Role } from './types'

function SignIn() {
  const {session, signIn} = useSession()
  const navigate = useNavigate(), location = useLocation()
  const [login, setLogin] = useState(''), [password, setPassword] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>()
  if (session) return <Navigate to={roleHome[session.role]} replace/>
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(undefined)
    try {
      const current = await signIn(login, password)
      const previous = (location.state as {from?: string} | null)?.from
      const prefix = roleHome[current.role].split('/')[1]
      navigate(previous?.startsWith(`/${prefix}`) ? previous : roleHome[current.role], {replace: true})
    } catch (error) {setError(error)} finally {setBusy(false)}
  }
  return <div className="signin-page"><header><Brand/></header><main className="signin-main"><div className="signin-grid"><div className="signin-intro"><h1>Sign in to SupportIQ</h1><p>Good support starts with a person.</p><ul className="signin-assurances"><li><Shield size={16}/><span>Every customer reply is reviewed and sent by a person.</span></li><li><Shield size={16}/><span>AI assists with intent classification and grounded citations.</span></li><li><Shield size={16}/><span>Order records remain strictly distinguished from AI text.</span></li></ul></div><div className="signin-card"><form onSubmit={submit} className="signin-form"><ErrorNotice error={error}/><div className="field"><label htmlFor="login-name">Login name</label><input id="login-name" autoComplete="username" autoFocus value={login} onChange={event => setLogin(event.target.value)} placeholder="e.g. staff-1" required maxLength={80}/></div><div className="field"><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required maxLength={200}/></div><Button type="submit" variant="primary" busy={busy} disabled={!login.trim() || !password}>Sign in<ArrowRight size={16}/></Button></form><p className="signin-note"><Shield size={15}/>Demo accounts: staff-1, manager-1, admin-1, customer-1</p></div></div></main><footer>Synthetic data · SupportIQ demo</footer></div>
}

export function Shell({area, children}: {area: 'shop' | 'console' | 'admin'; children: ReactNode}) {
  const {session, signOut} = useSession()
  const [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false)
  const links = area === 'shop' ? [{to: '/shop', label: 'Products', Icon: ShoppingBag, end: true}, {to: '/shop/orders', label: 'My orders', Icon: Inbox}, {to: '/shop/support', label: 'Support', Icon: UserRound}] : area === 'admin' ? [{to: '/admin/accounts', label: 'Accounts', Icon: Users}, {to: '/admin/versions', label: 'Versions', Icon: Layers}] : [{to: '/console', label: 'Tickets', Icon: Inbox, end: false}, ...(session?.role === 'manager' ? [{to: '/console/reports', label: 'Reports', Icon: BarChart3}] : [])]
  const location = useLocation()
  return <div className={`app ${area}-app`}><a className="skip-link" href="#main-content">Skip to content</a><header className="app-header"><Link to={area === 'shop' ? '/shop' : area === 'admin' ? '/admin/accounts' : '/console'} className="brand-link">{area === 'shop' ? <span className="brand"><ShoppingBag size={23} strokeWidth={1.5}/><strong>Demo Shop</strong><span className="brand-area shop-byline">by SupportIQ</span></span> : <Brand area={area === 'admin' ? 'Admin' : 'Console'}/>}</Link><nav aria-label={`${humanize(area)} navigation`}>{links.map(({to,label,Icon,end}) => <NavLink key={to} to={to} end={end} className={({isActive}) => (to === '/console' ? !location.pathname.includes('/reports') : isActive) ? 'nav-link active' : 'nav-link'}><Icon size={16}/>{label}</NavLink>)}</nav><div className="account-menu"><Link to="/profile" className="account-name profile-link" aria-label="Open user profile"><UserRound size={16}/>{session?.display_name}<span className="muted account-role">{area === 'shop' ? '' : humanize(session?.role || '')}</span></Link><Button variant="ghost" busy={busy} onClick={async () => {setBusy(true); try {await signOut()} catch(error) {setError(error)} finally {setBusy(false)}}}><LogOut size={15}/><span>Sign out</span></Button></div></header>{Boolean(error) && <ErrorNotice error={error}/>}<main id="main-content" className={area === 'console' ? 'console-main' : 'content-main'}>{children}</main>{area === 'shop' && <footer className="shop-footer"><span>Demo Shop</span><span>Synthetic data · Read-only catalog</span></footer>}</div>
}

function Protected({roles, children}: {roles: Role[]; children: ReactNode}) {
  const {session, loading, error} = useSession(), location = useLocation()
  if (loading) return <Loading label="Checking your session"/>
  if (error) return <ErrorNotice error={error} retry={() => window.location.reload()}/>
  if (!session) return <Navigate to="/sign-in" state={{from: location.pathname + location.search + location.hash}} replace/>
  if (!roles.includes(session.role)) return <div className="permission-page"><Brand/><ErrorNotice error={new ApiError(403, `This area is for ${roles.join(' and ')} accounts.`)}/><Link className="button primary" to={roleHome[session.role]}>Go to your workspace</Link></div>
  return children
}

interface ProfileData extends Session {email:string;phone:string;address:string;avatar_data_url:string|null}
function Profile() {
 const {session}=useSession(), client=useQueryClient(), location=useLocation()
 const requireContact = Boolean((location.state as {requireContact?:boolean}|null)?.requireContact)
 const [form,setForm]=useState<ProfileData|null>(null),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false),[error,setError]=useState<unknown>()
 useEffect(()=>{let active=true;api<ProfileData>('/v1/profile').then(value=>{if(active)setForm(value)}).catch(error=>{if(active)setError(error)});return()=>{active=false}},[])
 if(!session)return null
 const area=session.role==='customer'?'shop':session.role==='admin'?'admin':'console'
 const change=(key:string,value:string|null)=>{setForm(previous=>previous?{...previous,[key]:value}:previous);setSaved(false)}
 async function avatar(file?:File){
  if(!file)return
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){setError(new Error('Choose a PNG, JPEG or WebP image up to 5 MB.'));return}
  try{const image=await createImageBitmap(file);const canvas=document.createElement('canvas');canvas.width=192;canvas.height=192;const context=canvas.getContext('2d')!;const side=Math.min(image.width,image.height);context.drawImage(image,(image.width-side)/2,(image.height-side)/2,side,side,0,0,192,192);image.close();const value=canvas.toDataURL('image/webp',.8);if(value.length>44000)throw new Error('Choose a simpler or smaller image.');change('avatar_data_url',value);setError(undefined)}catch(error){setError(error)}
 }
 async function save(event:FormEvent){
  event.preventDefault();if(!form)return;setBusy(true);setSaved(false);setError(undefined)
  try{const {display_name,email,phone,address,avatar_data_url}=form;const updated=await api<ProfileData>('/v1/profile',{method:'PATCH',body:JSON.stringify({display_name:display_name.trim(),email,phone,address,avatar_data_url})});client.setQueryData(['session'],{account_id:updated.account_id,display_name:updated.display_name,role:updated.role});setForm(updated);setSaved(true)}catch(error){setError(error)}finally{setBusy(false)}
 }
 return <Shell area={area}><div className="profile-content"><Link className="back-link" to={roleHome[session.role]}>Back to workspace</Link><div className="page-heading"><div><h1>Profile</h1><p>Manage your account information.</p></div></div><ErrorNotice error={error}/>{!form?<Loading label="Loading profile"/>:<section className="profile-panel"><form onSubmit={save}>{requireContact && (!form.phone.trim() || !form.address.trim()) && <div className="notice danger" role="alert">Please enter your phone number and address before buying.</div>}<div className="profile-photo-row"><div className="profile-avatar">{form.avatar_data_url?<img src={form.avatar_data_url} alt="Your avatar"/>:<span aria-hidden="true">{form.display_name.split(' ').map(part=>part[0]).slice(0,2).join('')}</span>}</div><div><label className="button secondary" htmlFor="profile-avatar">Change avatar</label><input className="sr-only" id="profile-avatar" type="file" accept="image/png,image/jpeg,image/webp" onChange={event=>{void avatar(event.target.files?.[0]);event.target.value=''}}/><p className="muted small">PNG, JPEG or WebP · Up to 5 MB</p>{form.avatar_data_url&&<Button type="button" variant="ghost" onClick={()=>change('avatar_data_url',null)}>Remove avatar</Button>}</div></div><div className="field"><label htmlFor="profile-name">Display name</label><input id="profile-name" value={form.display_name} onChange={event=>change('display_name',event.target.value)} maxLength={100} required autoComplete="name"/></div><div className="field"><label htmlFor="profile-email">Email</label><input id="profile-email" type="email" value={form.email} onChange={event=>change('email',event.target.value)} maxLength={254} autoComplete="email"/></div><div className="field"><label htmlFor="profile-phone">Phone number</label><input id="profile-phone" type="tel" aria-invalid={requireContact && !form.phone.trim()} aria-describedby={requireContact && !form.phone.trim() ? "phone-required" : undefined} value={form.phone} onChange={event=>change('phone',event.target.value)} maxLength={40} autoComplete="tel"/>{requireContact && !form.phone.trim() && <span id="phone-required" className="danger-text small">Phone number is required.</span>}</div><div className="field"><label htmlFor="profile-address">Address</label><textarea id="profile-address" rows={3} aria-invalid={requireContact && !form.address.trim()} aria-describedby={requireContact && !form.address.trim() ? "address-required" : undefined} value={form.address} onChange={event=>change('address',event.target.value)} maxLength={1000} autoComplete="street-address"/>{requireContact && !form.address.trim() && <span id="address-required" className="danger-text small">Address is required.</span>}</div><div className="form-bottom"><span role="status">{saved?'Profile saved.':''}</span><Button type="submit" variant="primary" busy={busy} disabled={!form.display_name.trim()}>Save changes</Button></div></form></section>}</div></Shell>
}

export default function App() {
  const {session} = useSession()
  return <Routes><Route path="/profile" element={<Protected roles={['customer','staff','manager','admin']}><Profile/></Protected>}/><Route path="/sign-in" element={<SignIn/>}/><Route path="/shop/*" element={<Protected roles={['customer']}><Shell area="shop"><Shop/></Shell></Protected>}/><Route path="/console/reports" element={<Protected roles={['manager']}><Shell area="console"><Reports/></Shell></Protected>}/><Route path="/console/*" element={<Protected roles={['staff','manager']}><Shell area="console"><Console/></Shell></Protected>}/><Route path="/admin/*" element={<Protected roles={['admin']}><Shell area="admin"><Admin/></Shell></Protected>}/><Route path="/" element={<Navigate to={session ? roleHome[session.role] : '/sign-in'} replace/>}/><Route path="*" element={<div className="permission-page"><Brand/><h1>Page not found</h1><Link to="/">Go to SupportIQ</Link></div>}/></Routes>
}
