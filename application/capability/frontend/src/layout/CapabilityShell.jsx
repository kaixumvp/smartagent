import { Avatar, Badge, Layout, Menu, Typography } from 'antd'
import {
  BellOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { navigation } from './navigation'

const { Header, Content, Sider } = Layout

export default function CapabilityShell({
  page,
  selectedPath,
  showHeading,
  onNavigate,
  children,
}) {
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
          selectedKeys={[selectedPath]}
          items={navigation}
          onClick={({ key }) => onNavigate(key)}
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
          {showHeading && (
            <div className="capability-content-heading">
              <span>{page.section}</span>
              <strong>{page.title}</strong>
              <small>统一管理 Agent 可调用的工具、服务连接与工作流。</small>
            </div>
          )}
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}
