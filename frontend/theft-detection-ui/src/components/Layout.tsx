import {
    BarChart3,
    Bell, Camera,
    Circle,
    History,
    LayoutDashboard,
    Menu,
    Shield,
    X
} from 'lucide-react';
import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/',          label: 'Dashboard',   icon: LayoutDashboard },
  { path: '/alerts',    label: 'Alerts',      icon: Bell            },
  { path: '/cameras',   label: 'Cameras',     icon: Camera          },
  { path: '/history',   label: 'History',     icon: History         },
  { path: '/analytics', label: 'Analytics',   icon: BarChart3       },
];

interface LayoutProps { children: React.ReactNode; }

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location  = useLocation();
  const [open, setOpen] = useState(true);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>

      {/* Sidebar */}
      <aside style={{
        width:      open ? '240px' : '64px',
        background: 'var(--bg-secondary)',
        borderRight:'1px solid var(--border)',
        display:    'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        position:   'fixed',
        height:     '100vh',
        zIndex:     100,
        overflow:   'hidden',
      }}>

        {/* Logo */}
        <div style={{
          padding:    '20px 16px',
          display:    'flex',
          alignItems: 'center',
          gap:        '12px',
          borderBottom: '1px solid var(--border)',
        }}>
          <div style={{
            width:          '36px',
            height:         '36px',
            background:     'linear-gradient(135deg, #3b82f6, #06b6d4)',
            borderRadius:   '10px',
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'center',
            flexShrink:     0,
          }}>
            <Shield size={20} color="white" />
          </div>
          {open && (
            <div>
              <div style={{ fontWeight: 700, fontSize: '14px', color: 'var(--text-primary)' }}>
                TheftGuard
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                AI Security Platform
              </div>
            </div>
          )}
        </div>

        {/* Live indicator */}
        {open && (
          <div style={{
            margin:     '12px 16px',
            padding:    '8px 12px',
            background: 'rgba(16,185,129,0.1)',
            border:     '1px solid rgba(16,185,129,0.2)',
            borderRadius: '8px',
            display:    'flex',
            alignItems: 'center',
            gap:        '8px',
          }}>
            <Circle size={8} fill="#10b981" color="#10b981" />
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>
              System Online
            </span>
          </div>
        )}

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '8px' }}>
          {navItems.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                style={{
                  display:        'flex',
                  alignItems:     'center',
                  gap:            '12px',
                  padding:        '10px 12px',
                  borderRadius:   '8px',
                  marginBottom:   '4px',
                  textDecoration: 'none',
                  background:     active ? 'rgba(59,130,246,0.15)' : 'transparent',
                  border:         active ? '1px solid rgba(59,130,246,0.3)' : '1px solid transparent',
                  color:          active ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  transition:     'all 0.15s ease',
                }}
              >
                <Icon size={18} style={{ flexShrink: 0 }} />
                {open && (
                  <span style={{ fontSize: '14px', fontWeight: active ? 600 : 400 }}>
                    {label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Toggle button */}
        <button
          onClick={() => setOpen(!open)}
          style={{
            margin:     '16px',
            padding:    '8px',
            background: 'var(--bg-card)',
            border:     '1px solid var(--border)',
            borderRadius: '8px',
            color:      'var(--text-secondary)',
            cursor:     'pointer',
            display:    'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {open ? <X size={16} /> : <Menu size={16} />}
        </button>
      </aside>

      {/* Main content */}
      <main style={{
        marginLeft: open ? '240px' : '64px',
        flex:       1,
        transition: 'margin-left 0.2s ease',
        minHeight:  '100vh',
        background: 'var(--bg-primary)',
      }}>

        {/* Top bar */}
        <header style={{
          padding:      '16px 24px',
          background:   'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)',
          display:      'flex',
          alignItems:   'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600 }}>
              {navItems.find(n => n.path === location.pathname)?.label || 'Dashboard'}
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
              Real-Time AI Theft Detection Platform
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              padding:    '6px 12px',
              background: 'rgba(59,130,246,0.1)',
              border:     '1px solid rgba(59,130,246,0.2)',
              borderRadius: '20px',
              fontSize:   '12px',
              color:      'var(--accent-blue)',
            }}>
              YOLOv8 Active
            </div>
            <div style={{
              width:        '32px',
              height:       '32px',
              borderRadius: '50%',
              background:   'linear-gradient(135deg, #3b82f6, #06b6d4)',
              display:      'flex',
              alignItems:   'center',
              justifyContent: 'center',
              fontSize:     '14px',
              fontWeight:   700,
              color:        'white',
            }}>
              N
            </div>
          </div>
        </header>

        {/* Page content */}
        <div style={{ padding: '24px' }}>
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;