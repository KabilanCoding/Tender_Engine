import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { IconContext } from '@phosphor-icons/react'
import App from './App'
import { startMotion } from './lib/motion'
import { startCursor } from './lib/cursor'
import '@fontsource-variable/outfit'
import '@fontsource-variable/sora'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
import './theme-dark.css'

startMotion()
startCursor()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* Phosphor icons: two-tone everywhere, so feature and navigation icons share one look */}
    <IconContext.Provider value={{ weight: 'duotone', size: 16 }}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </IconContext.Provider>
  </React.StrictMode>
)
