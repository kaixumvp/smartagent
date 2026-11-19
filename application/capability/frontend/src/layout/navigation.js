import { createElement } from 'react'
import {
  ApiOutlined,
  AppstoreOutlined,
  ApartmentOutlined,
  AuditOutlined,
  CloudServerOutlined,
} from '@ant-design/icons'

export const navigation = [
  {
    type: 'group',
    label: 'CAPABILITY',
    children: [
      { key: '/', icon: createElement(AppstoreOutlined), label: 'Tool Catalog' },
      { key: '/providers', icon: createElement(CloudServerOutlined), label: 'MCP Providers' },
      { key: '/api-services', icon: createElement(ApiOutlined), label: 'API Services' },
      { key: '/workflows', icon: createElement(ApartmentOutlined), label: 'Workflows' },
      { key: '/interactions', icon: createElement(AuditOutlined), label: '待办中心' },
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

export function currentPath(pathname) {
  if (pathname === '/') return '/'
  if (pathname.startsWith('/providers')) return '/providers'
  if (pathname.startsWith('/api-services')) return '/api-services'
  if (pathname.startsWith('/workflows')) return '/workflows'
  if (pathname.startsWith('/interactions')) return '/interactions'
  return '/'
}

export function pageFor(pathname) {
  return pageTitles.find(({ match }) => match.test(pathname)) || pageTitles[0]
}
