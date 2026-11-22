import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './api'
import type { Role, Session } from './types'

export const roleHome: Record<Role, string> = { customer: '/shop', staff: '/console', manager: '/console', admin: '/admin/accounts' }
interface SessionContextValue { session: Session | null | undefined; loading: boolean; error: unknown; signIn: (login: string, password: string) => Promise<Session>; signOut: () => Promise<void> }
const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({children}: {children: ReactNode}) {
  const client = useQueryClient()
  const query = useQuery({queryKey: ['session'], queryFn: async () => {
    try { return await api<Session>('/v1/sessions/current') } catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error }
  }, retry: false, staleTime: 60_000})
  useEffect(() => {
    const expired = () => { client.removeQueries({predicate: query => query.queryKey[0] !== 'session'}); client.setQueryData(['session'], null) }
    window.addEventListener('session-expired', expired)
    return () => window.removeEventListener('session-expired', expired)
  }, [client])
  const signIn = async (login_name: string, password: string) => {
    await client.cancelQueries()
    const session = await api<Session>('/v1/sessions', {method: 'POST', body: JSON.stringify({login_name, password})})
    client.removeQueries({predicate: query => query.queryKey[0] !== 'session'}); client.setQueryData(['session'], session)
    return session
  }
  const signOut = async () => {
    try { await api<void>('/v1/sessions/current', {method: 'DELETE'}) } catch (error) { if (!(error instanceof ApiError) || error.status !== 401) throw error }
    client.removeQueries({predicate: query => query.queryKey[0] !== 'session'}); client.setQueryData(['session'], null)
  }
  return <SessionContext.Provider value={{session: query.data, loading: query.isPending, error: query.error, signIn, signOut}}>{children}</SessionContext.Provider>
}
export function useSession() { const value = useContext(SessionContext); if (!value) throw new Error('Session provider missing'); return value }
