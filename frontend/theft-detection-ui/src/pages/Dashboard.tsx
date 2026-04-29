import { formatDistanceToNow } from 'date-fns';
import { Activity, AlertTriangle, Camera, Clock, Shield, TrendingUp } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Alert, alertsApi, Stats, statsApi } from '../services/api';

const StatCard: React.FC<{
  title: string;
  value: number | string;
  icon: React.ReactNode;
  color: string;
  subtitle?: string;
}> = ({ title, value, icon, color, subtitle }) => (
  <div style={{
    background:   'var(--bg-card)',
    border:       '1px solid var(--border)',
    borderRadius: '12px',
    padding:      '20px',
    display:      'flex',
    alignItems:   'center',
    gap:          '16px',
  }}>
    <div style={{
      width:          '48px',
      height:         '48px',
      borderRadius:   '12px',
      background:     `${color}20`,
      border:         `1px solid ${color}40`,
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'center',
      color:          color,
      flexShrink:     0,
    }}>
      {icon}
    </div>
    <div>
      <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)' }}>
        {value}
      </div>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
        {title}
      </div>
      {subtitle && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
          {subtitle}
        </div>
      )}
    </div>
  </div>
);

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const colors: Record<string, { bg: string; color: string }> = {
    HIGH:   { bg: 'rgba(239,68,68,0.15)',  color: '#ef4444' },
    MEDIUM: { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b' },
    LOW:    { bg: 'rgba(16,185,129,0.15)', color: '#10b981' },
  };
  const style = colors[severity] || colors.LOW;
  return (
    <span style={{
      padding:      '3px 8px',
      borderRadius: '20px',
      fontSize:     '11px',
      fontWeight:   600,
      background:   style.bg,
      color:        style.color,
    }}>
      {severity}
    </span>
  );
};

const Dashboard: React.FC = () => {
  const [stats,        setStats]        = useState<Stats | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([]);
  const [loading,      setLoading]      = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, alertsRes] = await Promise.all([
        statsApi.get(),
        alertsApi.getAll(),
      ]);
      setStats(statsRes.data);
      setRecentAlerts(alertsRes.data.slice(0, 8));
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Auto refresh every 5 seconds
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div style={{
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'center',
        height:         '60vh',
        flexDirection:  'column',
        gap:            '16px',
      }}>
        <div style={{
          width:        '40px',
          height:       '40px',
          border:       '3px solid var(--border)',
          borderTop:    '3px solid var(--accent-blue)',
          borderRadius: '50%',
          animation:    'spin 1s linear infinite',
        }} />
        <p style={{ color: 'var(--text-muted)' }}>Loading dashboard...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  const chartData = stats?.top_objects?.map(obj => ({
    name:  obj.object,
    count: obj.count,
  })) || [];

  const chartColors = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Stat cards */}
      <div style={{
        display:             'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap:                 '16px',
      }}>
        <StatCard
          title    ="Total Alerts"
          value    ={stats?.total_alerts ?? 0}
          icon     ={<AlertTriangle size={22} />}
          color    ="#ef4444"
          subtitle ="All time"
        />
        <StatCard
          title    ="Alerts Today"
          value    ={stats?.alerts_today ?? 0}
          icon     ={<Clock size={22} />}
          color    ="#f59e0b"
          subtitle ="Last 24 hours"
        />
        <StatCard
          title    ="Detections"
          value    ={stats?.total_detections ?? 0}
          icon     ={<Activity size={22} />}
          color    ="#3b82f6"
          subtitle ="Total events"
        />
        <StatCard
          title    ="Active Cameras"
          value    ={stats?.total_cameras ?? 0}
          icon     ={<Camera size={22} />}
          color    ="#10b981"
          subtitle ="Online now"
        />
        <StatCard
          title    ="High Severity"
          value    ={stats?.high_severity ?? 0}
          icon     ={<Shield size={22} />}
          color    ="#ef4444"
          subtitle ="Critical alerts"
        />
        <StatCard
          title    ="Medium Severity"
          value    ={stats?.medium_severity ?? 0}
          icon     ={<TrendingUp size={22} />}
          color    ="#f59e0b"
          subtitle ="Warning alerts"
        />
      </div>

      {/* Chart + Alert feed */}
      <div style={{
        display:             'grid',
        gridTemplateColumns: '1fr 1fr',
        gap:                 '16px',
      }}>

        {/* Top detected objects chart */}
        <div style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '12px',
          padding:      '20px',
        }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '16px' }}>
            Top Detected Objects
          </h3>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background:   '#1a2235',
                    border:       '1px solid #1e293b',
                    borderRadius: '8px',
                    color:        '#f1f5f9',
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {chartData.map((_, index) => (
                    <Cell key={index} fill={chartColors[index % chartColors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{
              height:         '200px',
              display:        'flex',
              alignItems:     'center',
              justifyContent: 'center',
              color:          'var(--text-muted)',
              fontSize:       '14px',
            }}>
              No detection data yet
            </div>
          )}
        </div>

        {/* Live alert feed */}
        <div style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '12px',
          padding:      '20px',
        }}>
          <div style={{
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'space-between',
            marginBottom:   '16px',
          }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600 }}>
              Live Alert Feed
            </h3>
            <div style={{
              display:    'flex',
              alignItems: 'center',
              gap:        '6px',
              fontSize:   '12px',
              color:      '#10b981',
            }}>
              <div style={{
                width:        '6px',
                height:       '6px',
                borderRadius: '50%',
                background:   '#10b981',
                animation:    'pulse 2s infinite',
              }} />
              Live
            </div>
          </div>

          <style>{`
            @keyframes pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.3; }
            }
          `}</style>

          <div style={{
            display:       'flex',
            flexDirection: 'column',
            gap:           '8px',
            maxHeight:     '220px',
            overflowY:     'auto',
          }}>
            {recentAlerts.length === 0 ? (
              <div style={{
                textAlign: 'center',
                color:     'var(--text-muted)',
                fontSize:  '14px',
                padding:   '40px 0',
              }}>
                No alerts yet — start detection
              </div>
            ) : (
              recentAlerts.map(alert => (
                <div
                  key={alert.id}
                  style={{
                    display:      'flex',
                    alignItems:   'center',
                    gap:          '10px',
                    padding:      '10px 12px',
                    background:   'var(--bg-secondary)',
                    borderRadius: '8px',
                    border:       `1px solid ${
                      alert.severity === 'HIGH'
                        ? 'rgba(239,68,68,0.2)'
                        : 'rgba(245,158,11,0.2)'
                    }`,
                  }}
                >
                  <div style={{
                    width:        '8px',
                    height:       '8px',
                    borderRadius: '50%',
                    background:   alert.severity === 'HIGH' ? '#ef4444' : '#f59e0b',
                    flexShrink:   0,
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize:     '13px',
                      fontWeight:   500,
                      color:        'var(--text-primary)',
                      whiteSpace:   'nowrap',
                      overflow:     'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      Person near {alert.object_name}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {alert.camera_id} •{' '}
                      {formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })}
                    </div>
                  </div>
                  <SeverityBadge severity={alert.severity} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;