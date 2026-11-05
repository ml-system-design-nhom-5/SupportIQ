import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './styles.css'
import App from './App'
import { SessionProvider } from './session'

const queryClient = new QueryClient({defaultOptions: {queries: {retry: false, refetchOnWindowFocus: false}, mutations: {retry: false}}})
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><SessionProvider><App/></SessionProvider></BrowserRouter></QueryClientProvider></React.StrictMode>)
