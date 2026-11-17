import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import 'antd/dist/reset.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#158b83',
          colorInfo: '#158b83',
          colorSuccess: '#26866e',
          colorWarning: '#d89042',
          colorError: '#d75d5d',
          colorBgLayout: '#f3f6f8',
          colorBgContainer: '#ffffff',
          colorBorder: '#e7edf1',
          colorText: '#29404f',
          colorTextSecondary: '#788895',
          borderRadius: 8,
          fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: {
            bodyBg: '#f3f6f8',
            headerBg: '#ffffff',
            siderBg: '#142b3a',
          },
          Menu: {
            darkItemBg: '#142b3a',
            darkSubMenuItemBg: '#142b3a',
            darkItemColor: '#b6c5cc',
            darkItemSelectedBg: '#ffffff14',
            darkItemSelectedColor: '#ffffff',
            darkItemHoverBg: '#ffffff0d',
          },
          Table: {
            headerBg: '#f8fafb',
            headerColor: '#71818c',
            rowHoverBg: '#f6f9fa',
          },
          Card: {
            headerBg: '#ffffff',
          },
        },
      }}
    >
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
