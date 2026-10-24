import { Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import ProtectedRoute from './components/common/ProtectedRoute'
import LoginPage from './pages/auth/LoginPage'
import DashboardPage from './pages/analyst/DashboardPage'
import ProjectEstimationPage from './pages/analyst/ProjectEstimationPage'
import TenderLayout from './features/tender/TenderLayout'
import { UploadPage as TenderUploadPage } from './features/tender/pages/Upload'
import { ProcessingPage as TenderProcessingPage } from './features/tender/pages/Processing'
import { ReportPage as TenderReportPage } from './features/tender/pages/Report'
import { HistoryPage as TenderHistoryPage } from './features/tender/pages/History'
import { TenderTigerPage } from './features/tender/pages/TenderTiger'
import { TenderTigerDetailPage } from './features/tender/pages/TenderTigerDetail'
import ProposalGeneratorPage from './pages/analyst/ProposalGeneratorPage'
import KnowledgeBasePage from './pages/admin/KnowledgeBasePage'
import CostParametersPage from './pages/admin/CostParametersPage'
import ProjectDetailPage from './pages/admin/ProjectDetailPage'
import KBSearchPage from './pages/admin/KBSearchPage'
import SettingsPage from './pages/admin/SettingsPage'
import PastProjectsPage from './pages/analyst/PastProjectsPage'
import ReportsPage from './pages/analyst/ReportsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="estimation" element={<ProjectEstimationPage />} />
          <Route path="tender" element={<TenderLayout />}>
            <Route index element={<TenderUploadPage />} />
            <Route path="processing/:runId" element={<TenderProcessingPage />} />
            <Route path="report/:runId" element={<TenderReportPage />} />
            <Route path="history" element={<TenderHistoryPage />} />
            <Route path="tiger" element={<TenderTigerPage />} />
            <Route path="tiger/:tid" element={<TenderTigerDetailPage />} />
          </Route>
          <Route path="proposals" element={<ProposalGeneratorPage />} />
          <Route path="past-projects" element={<PastProjectsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="knowledge-base" element={<KnowledgeBasePage />} />
            <Route path="knowledge-base/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="cost-parameters" element={<CostParametersPage />} />
            <Route path="kb-search" element={<KBSearchPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
