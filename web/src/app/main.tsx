import { createRoot } from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { TenantPage } from './features/tenants/TenantPage';
import './style.css';

createRoot(document.getElementById('root')!).render(
  <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#14634f' } }}>
    <TenantPage />
  </ConfigProvider>,
);
