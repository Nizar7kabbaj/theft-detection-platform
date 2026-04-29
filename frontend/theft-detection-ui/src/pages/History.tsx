import { formatDistanceToNow } from 'date-fns';
import React, { useEffect, useState } from 'react';
import { Detection, detectionsApi } from '../services/api';

const History: React.FC = () => {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    detectionsApi.getAll(100)
      .then(res => setDetections(res.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: '16px', fontSize: '14px', color: 'var(--text-muted)' }}>
        {detections.length} detection events
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
          Loading history...
        </div>
      ) : (
        <div style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '12px',
          overflow:     'hidden',
        }}>
          {/* Table header */}
          <div style={{
            display:             'grid',
            gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr',
            padding:             '12px 16px',
            background:          'var(--bg-secondary)',
            fontSize:            '12px',
            fontWeight:          600,
            color:               'var(--text-muted)',
            textTransform:       'uppercase',
            letterSpacing:       '0.05em',
          }}>
            <span>Object</span>
            <span>Confidence</span>
            <span>Camera</span>
            <span>Session</span>
            <span>Time</span>
          </div>

          {/* Table rows */}
          {detections.length === 0 ? (
            <div style={{
              textAlign: 'center',
              padding:   '40px',
              color:     'var(--text-muted)',
              fontSize:  '14px',
            }}>
              No detections yet — start the AI model
            </div>
          ) : (
            detections.map((det, idx) => (
              <div
                key={det.id}
                style={{
                  display:             'grid',
                  gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr',
                  padding:             '12px 16px',
                  borderTop:           '1px solid var(--border)',
                  fontSize:            '13px',
                  background:          idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  alignItems:          'center',
                }}
              >
                <span style={{ fontWeight: 500 }}>{det.class_name}</span>
                <span>
                  <span style={{
                    padding:      '2px 8px',
                    borderRadius: '20px',
                    background:   det.confidence > 0.8
                      ? 'rgba(16,185,129,0.15)'
                      : 'rgba(245,158,11,0.15)',
                    color: det.confidence > 0.8 ? '#10b981' : '#f59e0b',
                    fontSize: '12px',
                  }}>
                    {(det.confidence * 100).toFixed(1)}%
                  </span>
                </span>
                <span style={{ color: 'var(--text-muted)' }}>{det.camera_id}</span>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '11px' }}>
                  #{det.session_id.toString().slice(-6)}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>
                  {formatDistanceToNow(new Date(det.timestamp), { addSuffix: true })}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default History;