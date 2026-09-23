import { useState } from 'react'
import {
  Activity,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  GitBranch,
  Network,
  Play,
  ShieldCheck,
  Target,
} from 'lucide-react'

import { useCairnStore } from '../store'
import type { WorkspaceSection } from '../types'
import { isConfirmedFact } from './graphProjection'

const sections: Array<{ id: WorkspaceSection; label: string; icon: typeof GitBranch }> = [
  { id: 'exploration', label: 'Exploration', icon: GitBranch },
  { id: 'program', label: 'Program', icon: Network },
  { id: 'hypotheses', label: 'Hypotheses', icon: CircleHelp },
  { id: 'evidence', label: 'Evidence', icon: ShieldCheck },
]

export function Sidebar() {
  const [treeOpen, setTreeOpen] = useState(true)
  const section = useCairnStore((state) => state.section)
  const setSection = useCairnStore((state) => state.setSection)
  const project = useCairnStore((state) => state.project)
  const nodes = useCairnStore((state) => state.nodes)
  const intents = useCairnStore((state) => state.intents)
  const workers = useCairnStore((state) => state.workers)
  const runWorker = useCairnStore((state) => state.runWorker)
  const runningWorkerId = useCairnStore((state) => state.runningWorkerId)
  const facts = nodes.filter(isConfirmedFact).slice(0, 3)
  const visibleIntents = intents.filter((intent) => intent.status !== 'failed').slice(0, 4)
  const failures = intents.filter((intent) => intent.status === 'failed')

  return (
    <aside className="sidebar panel">
      <nav className="workspace-nav" aria-label="Workspace sections">
        {sections.map((item) => {
          const Icon = item.icon
          const count = item.id === 'hypotheses'
            ? nodes.filter((node) => node.kind === 'Hypothesis').length
            : item.id === 'evidence'
              ? nodes.filter((node) => ['Evidence', 'Observation'].includes(node.kind)).length
              : undefined
          return (
            <button
              key={item.id}
              className={section === item.id ? 'active' : ''}
              onClick={() => setSection(item.id)}
            >
              <Icon size={14} />
              <span>{item.label}</span>
              {count !== undefined ? <b>{count}</b> : null}
            </button>
          )
        })}
      </nav>

      <section className="exploration-tree">
        <div className="sidebar-section-title">
          <span>Investigation tree</span>
          <button title="Collapse tree" onClick={() => setTreeOpen((value) => !value)}>
            {treeOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        </div>
        {treeOpen ? (
          <div className="tree-body">
            <div className="tree-item root">
              <Target size={13} />
              <div><strong>Analysis goal</strong><span>{project?.goal}</span></div>
            </div>
            <div className="tree-branch">
              {facts.map((fact) => (
                <div className="tree-item fact" key={fact.id}>
                  <span className="tree-status" />
                  <div><strong>Verified fact</strong><span>{fact.label}</span></div>
                </div>
              ))}
              {visibleIntents.map((intent) => (
                <div className={`tree-item intent state-${intent.status}`} key={intent.id}>
                  <Activity size={12} />
                  <div><strong>{intent.status === 'open' ? 'Queued intent' : intent.status}</strong><span>{intent.description}</span></div>
                </div>
              ))}
              {failures.map((intent) => (
                <div className="tree-item failure" key={`failed-${intent.id}`}>
                  <span className="tree-status" />
                  <div><strong>Failed path</strong><span>{intent.description}</span></div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="worker-runtime">
        <div className="sidebar-section-title">
          <span>Runtime</span>
          <b>{workers.filter((worker) => worker.status === 'busy').length} active</b>
        </div>
        {workers.map((worker) => {
          const isRunning = runningWorkerId === worker.id
          return (
            <button
              className="worker-row"
              key={worker.id}
              onClick={() => void runWorker(worker.id)}
              disabled={Boolean(runningWorkerId)}
            >
              <span className={`worker-state ${isRunning || worker.status === 'busy' ? 'active' : ''}`} />
              <div>
                <strong>{worker.name}</strong>
                <span>{worker.driver} · {isRunning ? 'running' : worker.status}</span>
              </div>
              {isRunning ? <Activity className="spin" size={13} /> : <Play size={12} />}
            </button>
          )
        })}
      </section>
    </aside>
  )
}
