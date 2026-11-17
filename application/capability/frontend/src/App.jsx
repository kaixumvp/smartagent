import { Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Badge, Layout, Menu, Typography } from 'antd'
import {
  ApiOutlined,
  AppstoreOutlined,
  ApartmentOutlined,
  AuditOutlined,
  BellOutlined,
  CloudServerOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import ToolCatalog from './pages/ToolCatalog'
import ToolEditor from './pages/ToolEditor'
import Providers from './pages/Providers'
import ProviderDetail from './pages/ProviderDetail'
import ApiServices from './pages/ApiServices'
import Workflows from './pages/Workflows'
import WorkflowEditor from './pages/WorkflowEditor'
import InteractionInbox from './pages/InteractionInbox'
import './App.css'

const { Header, Content, Sider } = Layout

const navigation = [
  {
    type: 'group',
    label: 'CAPABILITY',
    children: [
      { key: '/', icon: <AppstoreOutlined />, label: 'Tool Catalog' },
      { key: '/providers', icon: <CloudServerOutlined />, label: 'MCP Providers' },
      { key: '/api-services', icon: <ApiOutlined />, label: 'API Services' },
      { key: '/workflows', icon: <ApartmentOutlined />, label: 'Workflows' },
      { key: '/interactions', icon: <AuditOutlined />, label: '待办中心' },
    ],
  },
]

const pageTitles = [
  { match: /^\/$/, title: 'Tool Catalog', section: '资源管理' },
  { match: /^\/(new|edit\/)/, title: 'Tool Editor', section: '资源管理' },
  { match: /^\/providers\/[^/]+$/, title: 'Provider Detail', section: '连接管理' },
  { match: /^\/providers$/, title: 'MCP Providers', section: '连接管理' },
  { match: /^\/api-services$/, title: 'API Services', section: '连接管理' },
  { match: /^\/workflows$/, title: 'Workflows', section: '自动化' },
  { match: /^\/interactions$/, title: '待办中心', section: '自动化' },
]

function currentPath(pathname) {
  if (pathname === '/') return '/'
  if (pathname.startsWith('/providers')) return '/providers'
  if (pathname.startsWith('/api-services')) return '/api-services'
  if (pathname.startsWith('/workflows')) return '/workflows'
  if (pathname.startsWith('/interactions')) return '/interactions'
  return '/'
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const editorRoute = /^\/workflows\/[^/]+$/.test(location.pathname)
  const page = pageTitles.find(({ match }) => match.test(location.pathname)) || pageTitles[0]

  if (editorRoute) {
    return (
      <Routes>
        <Route path="/workflows/:id" element={<WorkflowEditor />} />
      </Routes>
    )
  }

  return (
    <Layout className="capability-shell">
      <Sider className="capability-sider" width={228} breakpoint="lg" collapsedWidth={62}>
        <div className="capability-brand">
          <span className="capability-brand-mark">✦</span>
          <span>SMARTAGENT<small>CAPABILITY HUB</small></span>
        </div>
        <div className="capability-workspace">
          <Avatar shape="square" className="capability-workspace-avatar">C</Avatar>
          <span><strong>Capability Hub</strong><small>Registry Workspace</small></span>
        </div>
        <Menu
          className="capability-menu"
          mode="inline"
          theme="dark"
          selectedKeys={[currentPath(location.pathname)]}
          items={navigation}
          onClick={({ key }) => navigate(key)}
        />
        <div className="capability-sider-footer">
          <div className="capability-connection"><i />Registry 已连接</div>
          <div className="capability-user">
            <Avatar size={30}>A</Avatar>
            <span><strong>管理员</strong><small>Capability Admin</small></span>
            <SettingOutlined />
          </div>
        </div>
      </Sider>
      <Layout className="capability-main">
        <Header className="capability-topbar">
          <div className="capability-breadcrumb"><span>Capability</span><span>/</span><Typography.Text strong>{page.title}</Typography.Text></div>
          <div className="capability-top-actions">
            <span className="capability-top-status"><i />服务正常</span>
            <Badge dot offset={[-3, 3]}><BellOutlined /></Badge>
            <Avatar size={30}>A</Avatar>
          </div>
        </Header>
        <Content className="capability-content">
          {location.pathname === '/' && (
            <div className="capability-content-heading">
              <span>{page.section}</span>
              <strong>{page.title}</strong>
              <small>统一管理 Agent 可调用的工具、服务连接与工作流。</small>
            </div>
          )}
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
    </Layout>
  )
}
