import { Routes, Route, useNavigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import { ApiOutlined, AppstoreOutlined } from '@ant-design/icons'
import ToolCatalog from './pages/ToolCatalog'
import ToolEditor from './pages/ToolEditor'
import Providers from './pages/Providers'
import ProviderDetail from './pages/ProviderDetail'

const { Header, Content } = Layout

export default function App() {
  const navigate = useNavigate()

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
            { key: '/providers', icon: <ApiOutlined />, label: 'MCP Providers' },
          ]}
          onClick={(e) => navigate(e.key)}
        />
      </Header>
      <Content style={{ padding: 24, maxWidth: 1200, width: '100%', margin: '0 auto' }}>
        <Routes>
          <Route path="/" element={<ToolCatalog />} />
          <Route path="/new" element={<ToolEditor />} />
          <Route path="/edit/:id" element={<ToolEditor />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/providers/:id" element={<ProviderDetail />} />
        </Routes>
      </Content>
    </Layout>
  )
}
