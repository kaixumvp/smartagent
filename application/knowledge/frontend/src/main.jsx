import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

// Surface otherwise-silent errors so a broken request is visible instead of a no-op.
window.addEventListener('unhandledrejection', (e) => {
  console.error('Unhandled promise rejection:', e.reason)
})
window.addEventListener('error', (e) => {
  console.error('Global error:', e.error || e.message)
})

createRoot(document.getElementById('root')).render(<App />)