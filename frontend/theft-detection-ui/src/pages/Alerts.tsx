import { formatDistanceToNow } from 'date-fns';
import { Check, Filter, RefreshCw, Trash2 } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import { Alert, alertsApi } from '../services/api';

const Alerts: React.FC = () => {
  const [alerts,   setAlerts]   = useState<Alert[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [filter,   setFilter]   = useState<string>('ALL');

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await alertsApi.getAll(filter === 'ALL' ? undefined : filter);
      setAlerts(res.data);
    } catch {
      toast.error('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  const handleAcknowledge = async (id: string) => {
    try {
      await alertsApi.acknowledge(id);
      toast.success('Alert acknowledged');
      fetchAlerts();
    } catch {
      toast.error('Failed to acknowledge');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await alertsApi.delete(id);
      toast.success('Alert deleted');
      fetchAlerts();
    } catch {
      toast.error('Failed to delete');
    }
  };

  return (
    <div>
      <Toaster position="top-right" />

      {/* Filters */}
      <div style={{
        display:      'flex',
        alignItems:   'center',
        gap:          '12px',
        marginBottom: '20px',
        flexWrap:     'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <Filter size={16} />
          <span style={{ fontSize: '14px' }}>Filter:</span>
        </div>
        {['ALL', 'HIGH', 'MEDIUM'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding:      '6px 16px',
              borderRadius: '20px',
              border:       '1px solid',
              borderColor:  filter === f ? 'var(--accent-blue)' : 'var(--border)',
              background:   filter === f ? 'rgba(59,130,246,0.15)' : 'transparent',
              color:        filter === f ? 'var(--accent-blue)' : 'var(--text-secondary)',
              cursor:       'pointer',
              fontSize:     '13px',
              fontWeight:   filter === f ? 600 : 400,
            }}
          >
            {f}
          </button>
        ))}
        <button
          onClick={fetchAlerts}
          style={{
            marginLeft:   'auto',
            display:      'flex',
            alignItems:   'center',
            gap:          '6px',
            padding:      '6px 14px',
            borderRadius: '8px',
            border:       '1px solid var(--border)',
            background:   'transparent',
            color:        'var(--text-secondary)',
            cursor:       'pointer',
            fontSize:     '13px',
          }}
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Alerts count */}
      <div style={{ marginBottom: '16px', fontSize: '14px', color: 'var(--text-muted)' }}>
        {alerts.length} alert{alerts.length !== 1 ? 's' : ''} found
      </div>

      {/* Alert list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
          Loading alerts...
        </div>
      ) : alerts.length === 0 ? (
        <div style={{
          textAlign:    'center',
          padding:      '60px',
          background:   'var(--bg-card)',
          borderRadius: '12px',
          border:       '1px solid var(--border)',
          color:        'var(--text-muted)',
        }}>
          No alerts found
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {alerts.map(alert => (
            <div
              key={alert.id}
              style={{
                background:   'var(--bg-card)',
                border:       `1px solid ${
                  alert.severity === 'HIGH'
                    ? 'rgba(239,68,68,0.3)'
                    : 'rgba(245,158,11,0.3)'
                }`,
                borderLeft:   `4px solid ${
                  alert.severity === 'HIGH' ? '#ef4444' : '#f59e0b'
                }`,
                borderRadius: '10px',
                padding:      '16px',
                display:      'flex',
                alignItems:   'center',
                gap:          '16px',
                opacity:      alert.acknowledged ? 0.6 : 1,
              }}
            >
              {/* Severity indicator */}
              <div style={{
                width:          '42px',
                height:         '42px',
                borderRadius:   '10px',
                background:     alert.severity === 'HIGH'
                  ? 'rgba(239,68,68,0.15)'
                  : 'rgba(245,158,11,0.15)',
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'center',
                flexShrink:     0,
                fontSize:       '10px',
                fontWeight:     700,
                color:          alert.severity === 'HIGH' ? '#ef4444' : '#f59e0b',
              }}>
                {alert.severity}
              </div>

              {/* Alert details */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '4px' }}>
                  Person near {alert.object_name}
                </div>
                <div style={{
                  display:  'flex',
                  gap:      '16px',
                  flexWrap: 'wrap',
                  fontSize: '12px',
                  color:    'var(--text-muted)',
                }}>
                  <span>📷 {alert.camera_id}</span>
                  <span>🎯 {(alert.confidence * 100).toFixed(1)}% confidence</span>
                  <span>🕐 {formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })}</span>
                  {alert.acknowledged && (
                    <span style={{ color: '#10b981' }}>✓ Acknowledged</span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                {!alert.acknowledged && (
                  <button
                    onClick={() => handleAcknowledge(alert.id)}
                    style={{
                      padding:      '6px 12px',
                      borderRadius: '8px',
                      border:       '1px solid rgba(16,185,129,0.3)',
                      background:   'rgba(16,185,129,0.1)',
                      color:        '#10b981',
                      cursor:       'pointer',
                      display:      'flex',
                      alignItems:   'center',
                      gap:          '4px',
                      fontSize:     '12px',
                    }}
                  >
                    <Check size={14} />
                    Ack
                  </button>
                )}
                <button
                  onClick={() => handleDelete(alert.id)}
                  style={{
                    padding:      '6px 12px',
                    borderRadius: '8px',
                    border:       '1px solid rgba(239,68,68,0.3)',
                    background:   'rgba(239,68,68,0.1)',
                    color:        '#ef4444',
                    cursor:       'pointer',
                    display:      'flex',
                    alignItems:   'center',
                    gap:          '4px',
                    fontSize:     '12px',
                  }}
                >
                  <Trash2 size={14} />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Alerts;