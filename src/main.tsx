import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import {SsoHandler} from './auth/SsoHandler.tsx';
import './index.css';

// No router in this app (see src/auth/SsoHandler.tsx for why): a plain
// pathname check is enough to carve out the one extra "route" the
// Staff Portal SSO handoff needs.
const isSsoHandoff = window.location.pathname === '/auth/sso';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isSsoHandoff ? <SsoHandler /> : <App />}
  </StrictMode>,
);
