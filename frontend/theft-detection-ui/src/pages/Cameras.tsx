import { Camera, Plus, Trash2, Wifi, WifiOff } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import { camerasApi, Camera as CameraType } from '../services/api';

const Cameras: React.FC = () => {
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '', location: '', stream_url: '', status: 'active'
  });

  const fetchCameras = async () => {
    try {
      const res = await camerasApi.getAll();
      setCameras(res.data);
    } catch {
      toast.error('Failed to load cameras');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCameras(); }, []);

  const handleCreate = async () => {
    if (!form.name || !form.location) {
      toast.error('Name and location are required');
      return;
    }
    try {
      await camerasApi.create(form);
      toast.success('Camera added successfully');
      setShowForm(false);
      setForm({ name: '', location: '', stream_url: '', status: 'active' });
      fetchCameras();
    } catch {
      toast.error('Failed to add camera');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await camerasApi.delete(id);
      toast.success('Camera deleted');
      fetchCameras();
    } catch {
      toast.error('Failed to delete camera');
    }
  };

  const inputStyle: React.CSSProperties = {
    width:        '100%',
    padding:      '10px 12px',
    background:   'var(--bg-secondary)',
    border:       '1px solid var(--border)',
    borderRadius: '8px',
    color:        'var(--text-primary)',
    fontSize:     '14px',
    outline:      'none',
  };

  return (
    <div>
      <Toaster position="top-right" />

      {/* Header */}
      <div style={{
        display:        'flex',
        justifyContent: 'space-between',
        alignItems:     'center',
        marginBottom:   '20px',
      }}>
        <div style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
          {cameras.length} camera{cameras.length !== 1 ? 's' : ''} registered
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            display:      'flex',
            alignItems:   'center',
            gap:          '8px',
            padding:      '8px 16px',
            borderRadius: '8px',
            border:       'none',
            background:   'var(--accent-blue)',
            color:        'white',
            cursor:       'pointer',
            fontSize:     '14px',
            fontWeight:   500,
          }}
        >
          <Plus size={16} />
          Add Camera
        </button>
      </div>

      {/* Add camera form */}
      {showForm && (
        <div style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--accent-blue)',
          borderRadius: '12px',
          padding:      '20px',
          marginBottom: '20px',
        }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '16px' }}>
            Add New Camera
          </h3>
          <div style={{
            display:             'grid',
            gridTemplateColumns: '1fr 1fr',
            gap:                 '12px',
            marginBottom:        '12px',
          }}>
            <div>
              <label style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px', display: 'block' }}>
                Camera Name *
              </label>
              <input
                style={inputStyle}
                placeholder="Camera-01"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px', display: 'block' }}>
                Location *
              </label>
              <input
                style={inputStyle}
                placeholder="Main Entrance"
                value={form.location}
                onChange={e => setForm({ ...form, location: e.target.value })}
              />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px', display: 'block' }}>
                Stream URL (optional)
              </label>
              <input
                style={inputStyle}
                placeholder="rtsp://192.168.1.100/stream"
                value={form.stream_url}
                onChange={e => setForm({ ...form, stream_url: e.target.value })}
              />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px', display: 'block' }}>
                Status
              </label>
              <select
                style={inputStyle}
                value={form.status}
                onChange={e => setForm({ ...form, status: e.target.value })}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleCreate}
              style={{
                padding:      '8px 20px',
                borderRadius: '8px',
                border:       'none',
                background:   'var(--accent-blue)',
                color:        'white',
                cursor:       'pointer',
                fontSize:     '14px',
                fontWeight:   500,
              }}
            >
              Save Camera
            </button>
            <button
              onClick={() => setShowForm(false)}
              style={{
                padding:      '8px 20px',
                borderRadius: '8px',
                border:       '1px solid var(--border)',
                background:   'transparent',
                color:        'var(--text-secondary)',
                cursor:       'pointer',
                fontSize:     '14px',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Camera grid */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
          Loading cameras...
        </div>
      ) : cameras.length === 0 ? (
        <div style={{
          textAlign:    'center',
          padding:      '60px',
          background:   'var(--bg-card)',
          borderRadius: '12px',
          border:       '1px solid var(--border)',
        }}>
          <Camera size={40} color="var(--text-muted)" style={{ marginBottom: '12px' }} />
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            No cameras registered yet
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: '12px', marginTop: '4px' }}>
            Click "Add Camera" to get started
          </p>
        </div>
      ) : (
        <div style={{
          display:             'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap:                 '16px',
        }}>
          {cameras.map(camera => (
            <div
              key={camera.id}
              style={{
                background:   'var(--bg-card)',
                border:       '1px solid var(--border)',
                borderRadius: '12px',
                padding:      '20px',
              }}
            >
              {/* Camera header */}
              <div style={{
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'space-between',
                marginBottom:   '12px',
              }}>
                <div style={{
                  width:          '40px',
                  height:         '40px',
                  borderRadius:   '10px',
                  background:     camera.status === 'active'
                    ? 'rgba(16,185,129,0.15)'
                    : 'rgba(100,116,139,0.15)',
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'center',
                  color:          camera.status === 'active' ? '#10b981' : '#64748b',
                }}>
                  <Camera size={20} />
                </div>
                <div style={{
                  display:    'flex',
                  alignItems: 'center',
                  gap:        '6px',
                  fontSize:   '12px',
                  color:      camera.status === 'active' ? '#10b981' : '#64748b',
                }}>
                  {camera.status === 'active'
                    ? <Wifi size={14} />
                    : <WifiOff size={14} />
                  }
                  {camera.status}
                </div>
              </div>

              <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                {camera.name}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                📍 {camera.location}
              </div>
              {camera.stream_url && (
                <div style={{
                  fontSize:     '11px',
                  color:        'var(--text-muted)',
                  fontFamily:   'monospace',
                  background:   'var(--bg-secondary)',
                  padding:      '6px 8px',
                  borderRadius: '6px',
                  marginBottom: '12px',
                  overflow:     'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace:   'nowrap',
                }}>
                  {camera.stream_url}
                </div>
              )}

              <button
                onClick={() => handleDelete(camera.id)}
                style={{
                  width:        '100%',
                  padding:      '8px',
                  borderRadius: '8px',
                  border:       '1px solid rgba(239,68,68,0.3)',
                  background:   'rgba(239,68,68,0.05)',
                  color:        '#ef4444',
                  cursor:       'pointer',
                  display:      'flex',
                  alignItems:   'center',
                  justifyContent: 'center',
                  gap:          '6px',
                  fontSize:     '13px',
                }}
              >
                <Trash2 size={14} />
                Remove Camera
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Cameras;