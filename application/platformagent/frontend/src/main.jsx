import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConfigProvider } from 'antd';
import App from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <ConfigProvider
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
    }}
  >
    <App />
  </ConfigProvider>,
);
