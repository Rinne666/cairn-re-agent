import { useEffect } from 'react'
import { Boxes, DatabaseZap, Plus, TriangleAlert } from 'lucide-react'

import { WS } from './api'
import { GraphCanvas } from './components/GraphCanvas'
import { ActivityPanel } from './components/ActivityPanel'
import { Inspector } from './components/Inspector'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { useCairnStore } from './store'

export default function App() {
  const loadProjects = useCairnStore((state) => state.loadProjects)
  const createDemo = useCairnStore((state) => state.createDemo)
  const project = useCairnStore((state) => state.project)
  const loading = useCairnStore((state) => state.loading)
  const error = useCairnStore((state) => state.error)
  const refresh = useCairnStore((state) => state.refresh)

  useEffect(() => { void loadProjects() }, [loadProjects])
  useEffect(() => {
    if (!project) return
    const socket = new WebSocket(`${WS}/projects/${project.id}/events`)
    let refreshTimer: number | undefined
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as { kind: string }
      if (event.kind !== 'heartbeat') {
        window.clearTimeout(refreshTimer)
        refreshTimer = window.setTimeout(() => void refresh(), 120)
      }
    }
    return () => {
      window.clearTimeout(refreshTimer)
      socket.close()
    }
  }, [project, refresh])

  if (!project) {
    return (
      <main className="welcome-shell">
        <div className="welcome-grid" />
        <section className="welcome-card">
          <div className="brand-mark large"><Boxes size={32} /></div>
          <span className="overline">Autonomous reverse engineering</span>
          <h1>Reason in evidence.<br />Search in graphs.</h1>
          <p>Cairn keeps program state, evidence, and exploration outside the agent so long investigations can recover, branch, and verify.</p>
          <button onClick={createDemo} disabled={loading}>
            {loading ? <DatabaseZap className="spin" size={17} /> : <Plus size={17} />}
            Initialize demo case
          </button>
          {error ? <div className="welcome-error"><TriangleAlert size={14} /> {error}. Is the API running?</div> : null}
        </section>
      </main>
    )
  }

  return (
    <div className="app-shell">
      <Topbar />
      <main className="workspace-grid">
        <Sidebar />
        <GraphCanvas />
        <Inspector />
      </main>
      <ActivityPanel />
      {error ? <div className="toast-error"><TriangleAlert size={14} /> {error}</div> : null}
    </div>
  )
}
