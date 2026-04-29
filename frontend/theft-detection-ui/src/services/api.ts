import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  alert_id: string;
  session_id: number;
  timestamp: string;
  camera_id: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  object_name: string;
  confidence: number;
  acknowledged: boolean;
  snapshot_path: string | null;
}

export interface Camera {
  id: string;
  name: string;
  location: string;
  stream_url: string | null;
  status: string;
  created_at: string;
}

export interface Stats {
  total_alerts: number;
  total_detections: number;
  total_cameras: number;
  alerts_today: number;
  high_severity: number;
  medium_severity: number;
  top_objects: { object: string; count: number }[];
}

export interface Detection {
  id: string;
  session_id: number;
  frame_index: number;
  timestamp: string;
  camera_id: string;
  class_name: string;
  confidence: number;
  bbox: { x1: number; y1: number; x2: number; y2: number };
}

// ── API calls ──────────────────────────────────────────────────────────────────

export const alertsApi = {
  getAll: (severity?: string) =>
    api.get<Alert[]>('/api/alerts/', { params: severity ? { severity } : {} }),
  getRecent: () =>
    api.get<Alert[]>('/api/stats/recent'),
  acknowledge: (id: string) =>
    api.patch(`/api/alerts/${id}/acknowledge`),
  delete: (id: string) =>
    api.delete(`/api/alerts/${id}`),
};

export const camerasApi = {
  getAll: () => api.get<Camera[]>('/api/cameras/'),
  create: (data: Omit<Camera, 'id' | 'created_at'>) =>
    api.post<{ id: string; message: string }>('/api/cameras/', data),
  delete: (id: string) => api.delete(`/api/cameras/${id}`),
};

export const statsApi = {
  get: () => api.get<Stats>('/api/stats/'),
};

export const detectionsApi = {
  getAll: (limit = 50) =>
    api.get<Detection[]>('/api/detections/', { params: { limit } }),
};

export default api;