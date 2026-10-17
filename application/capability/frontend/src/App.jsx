import { Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import { ApiOutlined, AppstoreOutlined, ApartmentOutlined, AuditOutlined } from '@ant-design/icons'
import ToolCatalog from './pages/ToolCatalog'
import ToolEditor from './pages/ToolEditor'
import Providers from './pages/Providers'
import ProviderDetail from './pages/ProviderDetail'
import ApiServices from './pages/ApiServices'
import Workflows from './pages/Workflows'
import WorkflowEditor from './pages/WorkflowEditor'
import InteractionInbox from './pages/InteractionInbox'

const { Header, Content } = Layout

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()

  if (/^\/workflows\/[^/]+$/.test(location.pathname)) {
    return (
      <Routes>
        <Route path="/workflows/:id" element={<WorkflowEditor />} />
      </Routes>
    )
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 700, fontSize: 18, marginRight: 32 }}>
          ◈ Capability Registry
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          style={{ flex: 1, minWidth: 0 }}
          items={[
            { key: '/', icon: <AppstoreOutlined />, label: 'Tool Catalog' },
            { key: '/api-services', icon: <ApiOutlined />, label: 'API Services' },
            { key: '/providers', icon: <ApiOutlined />, label: 'MCP Providers' },
            { key: '/workflows', icon: <ApartmentOutlined />, label: 'Workflows' },
            { key: '/interactions', icon: <AuditOutlined />, label: '待办中心' },
          ]}
          onClick={(e) => navigate(e.key)}
        />
      </Header>
      <Content style={{ padding: 24, maxWidth: 1200, width: '100%', margin: '0 auto' }}>
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
      </Content>
    </Layout>
  )
}
