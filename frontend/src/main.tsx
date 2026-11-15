import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './style.css'
import './styles/mission-tokens.css'
import './styles/local-mission.css'
import { assetUrl } from './api'

// Start the complete local overview before MissionControl's lazy chunk mounts.
const overview=document.createElement('link')
overview.rel='preload';overview.as='image';overview.crossOrigin='anonymous'
overview.href=assetUrl('/api/assets/mars-global.jpg')
overview.setAttribute('fetchpriority','high');document.head.appendChild(overview)

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
