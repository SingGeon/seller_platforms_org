import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import Layout from './components/Layout'
import { loadData, setSeller } from './data/api'
import { AuthError, authStatus, getToken, me, setOnAuthLost, type Seller } from './data/client'
import './index.css'
import Company from './pages/Company'
import Config from './pages/Config'
import Home from './pages/Home'
import Leads from './pages/Leads'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import Runs from './pages/Runs'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'leads', element: <Leads /> },
      { path: 'leads/:id', element: <Company /> },
      { path: 'pipeline', element: <Pipeline /> },
      { path: 'config', element: <Config /> },
      { path: 'runs', element: <Runs /> },
    ],
  },
])

type Gate = { state: 'loading' } | { state: 'login'; firstRun: boolean } | { state: 'app' }

/** Login first (seller accounts in PostgreSQL), then load the data. Without a reachable API the app shows demo data. */
function App() {
  const [gate, setGate] = useState<Gate>({ state: 'loading' })

  const enter = async (seller: Seller | null) => {
    setSeller(seller)
    try {
      await loadData()
      setGate({ state: 'app' })
    } catch (err) {
      if (err instanceof AuthError) setGate({ state: 'login', firstRun: false })
      else throw err
    }
  }

  useEffect(() => {
    setOnAuthLost(() => setGate({ state: 'login', firstRun: false }))
    const start = async () => {
      if (import.meta.env.VITE_USE_MOCK === 'true') return enter(null)
      let status
      try {
        status = await authStatus()
      } catch {
        return enter(null) // API down: demo data
      }
      if (!status.auth_required) return enter(null)
      if (!status.has_sellers) return setGate({ state: 'login', firstRun: true })
      if (getToken()) {
        try {
          return enter(await me())
        } catch {
          // expired or revoked token
        }
      }
      setGate({ state: 'login', firstRun: false })
    }
    void start()
  }, [])

  if (gate.state === 'loading') return <div className="flex h-full items-center justify-center text-muted">Se încarcă…</div>
  if (gate.state === 'login') return <Login firstRun={gate.firstRun} onDone={(s) => void enter(s)} />
  return <RouterProvider router={router} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
