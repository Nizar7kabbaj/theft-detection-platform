import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL || "https://localhost";
const COOKIE = __ENV.ACCESS_COOKIE || "__Host-access_token";
const PEAK = Number(__ENV.PEAK_RPS || 60);
const PASSWORD = open("/secrets/password").trim();
const CAMERAS = ["cam-load-1", "cam-load-2", "cam-load-3", "cam-load-4"];
const SEVERITIES = ["SEVERITY_NOTICE", "SEVERITY_WARNING", "SEVERITY_CRITICAL"];

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
  scenarios: {
    api: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { target: 5, duration: "1m" },
        { target: PEAK, duration: "1m" },
        { target: PEAK, duration: "4m" },
        { target: 0, duration: "30s" },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:list}": ["p(95)<500"],
    "http_req_duration{name:count}": ["p(95)<500"],
    "http_req_duration{name:detail}": ["p(95)<500"],
  },
};

function pick(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function filters() {
  const roll = Math.random();
  if (roll < 0.4) {
    return `camera_id=${pick(CAMERAS)}`;
  }
  if (roll < 0.7) {
    return `severity=${pick(SEVERITIES)}`;
  }
  return "";
}

export function setup() {
  const login = http.post(
    `${BASE}/auth/login`,
    JSON.stringify({ username: "viewer", password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, responseType: "text" },
  );
  check(login, { "login ok": (r) => r.status === 200 });
  const jar = login.cookies[COOKIE];
  if (!jar || jar.length === 0) {
    throw new Error(`login returned status ${login.status} and no ${COOKIE}`);
  }
  const token = jar[0].value;
  const page = http.get(`${BASE}/api/v1/alerts?limit=200`, {
    headers: { Authorization: `Bearer ${token}` },
    responseType: "text",
  });
  const body = page.json();
  const items = body.items || body.alerts || body.data || [];
  const ids = items.map((item) => item.id || item._id).filter(Boolean);
  if (ids.length === 0) {
    throw new Error(`no alert ids from list, status ${page.status}, keys ${Object.keys(body)}`);
  }
  return { token, ids };
}

export default function (data) {
  const params = { headers: { Authorization: `Bearer ${data.token}` } };
  const roll = Math.random();
  if (roll < 0.5) {
    http.get(`${BASE}/api/v1/alerts?limit=50&${filters()}`, { ...params, tags: { name: "list" } });
  } else if (roll < 0.7) {
    http.get(`${BASE}/api/v1/alerts/count?${filters()}`, { ...params, tags: { name: "count" } });
  } else {
    http.get(`${BASE}/api/v1/alerts/${pick(data.ids)}`, { ...params, tags: { name: "detail" } });
  }
}
