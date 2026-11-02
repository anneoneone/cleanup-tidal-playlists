import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import Backups from "./pages/Backups";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import NotFound from "./pages/NotFound";
import PlanPage from "./pages/PlanPage";
import PlaylistDetail from "./pages/PlaylistDetail";
import Playlists from "./pages/Playlists";
import RunDetail from "./pages/RunDetail";
import Settings from "./pages/Settings";
import Sync from "./pages/Sync";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="sync" element={<Sync />} />
        <Route path="plans/:runId" element={<PlanPage />} />
        <Route path="playlists" element={<Playlists />} />
        <Route path="playlists/:playlistId" element={<PlaylistDetail />} />
        <Route path="history" element={<History />} />
        <Route path="history/:runId" element={<RunDetail />} />
        <Route path="backups" element={<Backups />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
