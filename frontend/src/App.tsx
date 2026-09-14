import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AiQaPage } from './pages/AiQaPage'
import { AppConfigPage } from './pages/AppConfigPage'
import { FeedbackReviewPage } from './pages/FeedbackReviewPage'
import { LogsPage } from './pages/LogsPage'
import { ModelConfigPage } from './pages/ModelConfigPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<AiQaPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/system" element={<Navigate to="/system/app" replace />} />
        <Route path="/system/app" element={<AppConfigPage />} />
        <Route path="/system/model" element={<ModelConfigPage />} />
        <Route path="/feedback" element={<Navigate to="/feedback/review" replace />} />
        <Route path="/feedback/review" element={<FeedbackReviewPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
