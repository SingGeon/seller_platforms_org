import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import Layout from './components/Layout'
import './index.css'
import Company from './pages/Company'
import Config from './pages/Config'
import Home from './pages/Home'
import Leads from './pages/Leads'
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
