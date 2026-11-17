import { Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import ApiServices from './pages/ApiServices'
import InteractionInbox from './pages/InteractionInbox'
import ProviderDetail from './pages/ProviderDetail'
import Providers from './pages/Providers'
import ToolCatalog from './pages/ToolCatalog'
import ToolEditor from './pages/ToolEditor'
import WorkflowEditor from './pages/WorkflowEditor'
import Workflows from './pages/Workflows'
import CapabilityShell from './layout/CapabilityShell'
import { currentPath, pageFor } from './layout/navigation'
import './App.css'

export default function App() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const editorRoute = /^\/workflows\/[^/]+$/.test(pathname)
  const page = pageFor(pathname)

  if (editorRoute) {
    return (
      <Routes>
        <Route path="/workflows/:id" element={<WorkflowEditor />} />
      </Routes>
    )
  }

  return (
    <CapabilityShell
      page={page}
      selectedPath={currentPath(pathname)}
      showHeading={pathname === '/'}
      onNavigate={navigate}
    >
      <Routes>
        <Route path="/" element={<ToolCatalog />} />
        <Route path="/new" element={<ToolEditor />} />
        <Route path="/edit/:id" element={<ToolEditor />} />
        <Route path="/api-services" element={<ApiServices />} />
        <Route path="/providers" element={<Providers />} />
        <Route path="/providers/:id" element={<ProviderDetail />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/:id" element={<WorkflowEditor />} />
        <Route path="/interactions" element={<InteractionInbox />} />
      </Routes>
    </CapabilityShell>
  )
}
