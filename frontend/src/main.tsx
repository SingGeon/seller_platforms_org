import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from 'react-router'
import { SessionProvider, useSession } from './auth/session'
import Layout from './components/Layout'
import './index.css'
import Account from './pages/Account'
import Admin from './pages/Admin'
import Company from './pages/Company'
import Config from './pages/Config'
import Home from './pages/Home'
import Leads from './pages/Leads'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import Runs from './pages/Runs'

function Splash({ text }: { text: string }) {
  return <div className="flex h-full items-center justify-center bg-ink text-white/60">{text}</div>
}

/** Logged-out visitors get the login on "/"; any other app page sends them there and back after login. */
function AppGate() {
  const { loading, seller, dataReady } = useSession()
  const location = useLocation()
  if (loading) return <Splash text="Se încarcă…" />
  if (!seller) return location.pathname === '/' ? <Login /> : <Navigate to="/" replace state={{ from: location.pathname + location.search }} />
  if (!dataReady) return <Splash text="Se încarcă lead-urile…" />
  return <Layout />
}

/** Admin pages: only accounts with role "admin" (created directly in the database). */
function AdminOnly({ children }: { children: ReactNode }) {
  const { seller } = useSession()
  return seller?.role === 'admin' ? children : <Navigate to="/" replace />
}

const router = createBrowserRouter([
  { path: '/login', element: <Navigate to="/" replace /> },
  { path: '/signup', element: <Navigate to="/" replace /> },
  {
    path: '/',
    element: <AppGate />,
    children: [
      { index: true, element: <Home /> },
      { path: 'leads', element: <Leads /> },
      { path: 'leads/:id', element: <Company /> },
      { path: 'pipeline', element: <Pipeline /> },
      { path: 'config', element: <Config /> },
      { path: 'runs', element: <Runs /> },
      { path: 'account', element: <Account /> },
      { path: 'admin', element: <AdminOnly><Admin /></AdminOnly> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>
  </StrictMode>,
)
