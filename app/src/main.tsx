import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { MockRoute } from './mock/MockRoute'

const isMock = location.pathname.replace(/\/$/, '') === '/mock'

createRoot(document.getElementById('root')!).render(<StrictMode>{isMock ? <MockRoute /> : <App />}</StrictMode>)
