import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp, Clock3, TerminalSquare } from 'lucide-react'

import { useCairnStore } from '../store'

const tabs = ['Activity', 'Tool calls', 'Timeline', 'Errors'] as const

export function ActivityPanel() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('Activity')
  const [collapsed, setCollapsed] = useState(false)
  const events = useCairnStore((state) => state.events)
  const intents = useCairnStore((state) => state.intents)
  const failures = events.filter((event) => event.kind.includes('failed'))

  const rows = activeTab === 'Errors'
    ? failures
    : activeTab === 'Tool calls'
      ? events.filter((event) => event.kind.startsWith('worker.'))
      : events

  return (
    <section className={`activity-panel ${collapsed ? 'collapsed' : ''}`}>
      <div className="activity-tabs">
        {tabs.map((tab) => (
          <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)}>
            {tab === 'Errors' && failures.length ? <AlertTriangle size={11} /> : null}
            {tab}
            {tab === 'Errors' ? <b>{failures.length}</b> : null}
          </button>
        ))}
        <span className="activity-summary">{intents.filter((intent) => intent.status === 'open').length} queued intents</span>
        <button className="collapse-activity" onClick={() => setCollapsed((value) => !value)} title="Toggle activity panel">
          {collapsed ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>
      {!collapsed ? (
        <div className="activity-body">
          {rows.slice(-12).reverse().map((event) => (
            <div className="activity-row" key={event.id}>
              <Clock3 size={11} />
              <code>{new Date(event.created_at).toLocaleTimeString([], { hour12: false })}</code>
              <strong>{event.kind}</strong>
              <span>{event.kind.startsWith('worker.') ? 'Worker runtime' : event.kind.startsWith('intent.') ? 'Search engine' : 'Graph store'}</span>
              <TerminalSquare size={11} />
              <code>{String(event.payload.worker_id ?? event.payload.node_id ?? event.id).slice(0, 12)}</code>
            </div>
          ))}
          {!rows.length ? <div className="activity-empty">No events in this category.</div> : null}
        </div>
      ) : null}
    </section>
  )
}
