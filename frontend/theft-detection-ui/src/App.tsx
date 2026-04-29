import React from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import Alerts from './pages/Alerts';
import Analytics from './pages/Analytics';
import Cameras from './pages/Cameras';
import Dashboard from './pages/Dashboard';
import History from './pages/History';

const App: React.FC = () => (
  <BrowserRouter>
    <Layout>
      <Routes>
        <Route path="/"          element={<Dashboard />} />
        <Route path="/alerts"    element={<Alerts    />} />
        <Route path="/cameras"   element={<Cameras   />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/history"   element={<History   />} />
      </Routes>
    </Layout>
  </BrowserRouter>
);

export default App;