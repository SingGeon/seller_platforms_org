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

function Splash({ title, text, action }: { title: string; text?: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 bg-ink px-6 text-center text-white" role="status">
      <p className="text-[20px] font-bold">{title}</p>
      {text && <p className="max-w-md text-white/60">{text}</p>}
      {action && (
        <button type="button" onClick={action.onClick} className="mt-3 h-10 border-2 border-orange bg-orange px-5 font-bold text-ink hover:bg-transparent hover:text-orange">
          {action.label}
        </button>
      )}
    </div>
  )
}

/** Logged-out visitors get the login on "/"; any other app page sends them there and back after login. */
function AppGate() {
  const { server, seller, dataReady, dataError, retry } = useSession()
  const location = useLocation()
  if (server === 'connecting')
    return <Splash title="Se conectează la server…" text="Dacă serverul a stat inactiv, pornirea lui poate dura până la un minut." />
  if (server === 'down')
    return (
      <Splash
        title="Serverul nu răspunde"
        text="Nu am putut contacta serverul LeadRadar. Datele nu pot fi afișate până nu revine."
        action={{ label: 'Reîncearcă', onClick: retry }}
      />
    )
  if (!seller) return location.pathname === '/' ? <Login /> : <Navigate to="/" replace state={{ from: location.pathname + location.search }} />
  if (dataError) return <Splash title="Lead-urile nu s-au putut încărca" text={dataError} action={{ label: 'Reîncearcă', onClick: retry }} />
  if (!dataReady) return <Splash title="Se încarcă lead-urile…" />
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
