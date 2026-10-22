import { Navigate, Route, Routes } from 'react-router'
import LoginPage from '../features/auth/LoginPage'
import ImportsPage from '../features/imports/ImportsPage'
import MemberPage from '../features/queue/MemberPage'
import OpportunityPage from '../features/queue/OpportunityPage'
import QueuePage from '../features/queue/QueuePage'
import AppShell from './AppShell'
import RequireAuth from './RequireAuth'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="queue" element={<QueuePage />} />
        <Route path="members/:memberId" element={<MemberPage />} />
        <Route path="opportunities/:opportunityId" element={<OpportunityPage />} />
        <Route
          path="imports"
          element={
            <RequireAuth role="ADMIN">
              <ImportsPage />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
