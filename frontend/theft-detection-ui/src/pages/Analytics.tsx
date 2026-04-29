import React, { useEffect, useState } from 'react';
import {
    Bar,
    BarChart,
    Cell, Legend,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip,
    XAxis, YAxis
} from 'recharts';
import { Stats, statsApi } from '../services/api';

const COLORS = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6'];

const Analytics: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    statsApi.get().then(res => setStats(res.data));
  }, []);

  const pieData = [
    { name: 'High',   value: stats?.high_severity   ?? 0 },
    { name: 'Medium', value: stats?.medium_severity  ?? 0 },
  ];

  const barData = stats?.top_objects?.map(o => ({
    name: o.object, count: o.count
  })) ?? [];

  const cardStyle: React.CSSProperties = {
    background:   'var(--bg-card)',
    border:       '1px solid var(--border)',
    borderRadius: '12px',
    padding:      '20px',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Summary numbers */}
      <div style={{
        display:             'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap:                 '16px',
      }}>
        {[
          { label: 'Total Alerts',      value: stats?.total_alerts     ?? 0, color: '#ef4444' },
          { label: 'Total Detections',  value: stats?.total_detections ?? 0, color: '#3b82f6' },
          { label: 'High Severity',     value: stats?.high_severity    ?? 0, color: '#ef4444' },
          { label: 'Medium Severity',   value: stats?.medium_severity  ?? 0, color: '#f59e0b' },
          { label: 'Active Cameras',    value: stats?.total_cameras    ?? 0, color: '#10b981' },
        ].map(item => (
          <div key={item.label} style={cardStyle}>
            <div style={{ fontSize: '28px', fontWeight: 700, color: item.color }}>
              {item.value}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {item.label}
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>

        {/* Bar chart */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '16px' }}>
            Detections by Object Type
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={barData}>
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: '#1a2235', border: '1px solid #1e293b',
                  borderRadius: '8px', color: '#f1f5f9',
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {barData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Pie chart */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '16px' }}>
            Alert Severity Distribution
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={4}
                dataKey="value"
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Legend
                formatter={(value) => (
                  <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                    {value}
                  </span>
                )}
              />
              <Tooltip
                contentStyle={{
                  background: '#1a2235', border: '1px solid #1e293b',
                  borderRadius: '8px', color: '#f1f5f9',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default Analytics;