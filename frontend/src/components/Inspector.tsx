import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  Braces,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  FileCode2,
  GitCommitHorizontal,
  ListTree,
  ShieldAlert,
} from 'lucide-react'

import { useCairnStore } from '../store'

const CodePanel = lazy(() => import('./CodePanel'))

const functionTabs = ['Overview', 'Decompiler', 'Assembly', 'Callers', 'Callees', 'Xrefs', 'Evidence', 'Hypotheses', 'Artifacts']
const hypothesisTabs = ['Overview', 'Evidence', 'Functions', 'Intents']

export function Inspector() {
  const [activeTab, setActiveTab] = useState('Overview')
  const nodes = useCairnStore((state) => state.nodes)
  const edges = useCairnStore((state) => state.edges)
  const selectedNodeId = useCairnStore((state) => state.selectedNodeId)
  const events = useCairnStore((state) => state.events)
  const node = nodes.find((item) => item.id === selectedNodeId) ?? null
  const isHypothesis = node?.kind === 'Hypothesis'
  const tabs = node?.kind === 'Function' ? functionTabs : isHypothesis ? hypothesisTabs : ['Overview', 'Evidence', 'Artifacts']

  useEffect(() => setActiveTab('Overview'), [selectedNodeId])

  const relations = useMemo(() => {
    if (!node) return { supporting: 0, contradicting: 0, related: 0 }
    const connected = edges.filter((edge) => edge.source_node_id === node.id || edge.target_node_id === node.id)
    return {
      supporting: connected.filter((edge) => edge.kind === 'supports').length,
      contradicting: connected.filter((edge) => edge.kind === 'contradicts').length,
      related: connected.length,
    }
  }, [edges, node])

  return (
    <aside className="inspector panel">
      <div className="inspector-header">
        <span>Inspector</span>
        {node ? <code>{node.kind}</code> : <span>Nothing selected</span>}
      </div>
      {node ? (
        <div className="inspector-content">
          <div className="entity-title">
            <div className={`entity-icon kind-${node.kind.toLowerCase()}`}>
              {node.kind === 'Function' ? <Braces size={16} /> : isHypothesis ? <CircleHelp size={16} /> : <Database size={15} />}
            </div>
            <div>
              <h2>{node.label}</h2>
              <code>{typeof node.properties.address === 'string' ? node.properties.address : node.entity_key}</code>
            </div>
          </div>

          <div className="inspector-tabs" role="tablist">
            {tabs.map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={activeTab === tab ? 'active' : ''}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTab === 'Decompiler' || activeTab === 'Assembly' ? (
            <section className="editor-panel">
              <div className="editor-meta">
                <span><FileCode2 size={12} /> {activeTab === 'Assembly' ? 'sub_401200.asm' : 'sub_401200.c'}</span>
                <code>artifact: decompile_401200</code>
              </div>
              <Suspense fallback={<div className="code-loading">Loading code view...</div>}>
                <CodePanel mode={activeTab === 'Assembly' ? 'assembly' : 'decompiler'} />
              </Suspense>
            </section>
          ) : activeTab === 'Overview' ? (
            <div className="overview-panel">
              <div className="summary-metrics">
                <div><span>Confidence</span><strong>{Math.round(node.confidence * 100)}%</strong></div>
                <div><span>Relations</span><strong>{relations.related}</strong></div>
                <div><span>Status</span><strong>{node.status}</strong></div>
              </div>

              {isHypothesis ? (
                <>
                  <section className="inspector-block hypothesis-summary">
                    <h3><CircleHelp size={13} /> Hypothesis statement</h3>
                    <p>{node.label}</p>
                    <div className="evidence-balance">
                      <span className="support"><CheckCircle2 size={12} /> {relations.supporting} supporting</span>
                      <span className="conflict"><ShieldAlert size={12} /> {relations.contradicting} contradicting</span>
                    </div>
                  </section>
                  <section className="inspector-block">
                    <h3><ListTree size={13} /> Unresolved questions</h3>
                    <ul className="question-list">
                      <li>Is a complete key schedule present?</li>
                      <li>Does the dynamic trace confirm all input bytes?</li>
                    </ul>
                  </section>
                </>
              ) : null}

              <section className="inspector-block">
                <h3><Database size={13} /> Properties</h3>
                <dl className="property-list">
                  {Object.entries(node.properties).filter(([key]) => key !== 'provenance').map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll('_', ' ')}</dt>
                      <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
              <section className="inspector-block provenance">
                <h3><GitCommitHorizontal size={13} /> Provenance</h3>
                <p>{node.created_by}</p>
                <code>{new Date(node.created_at).toLocaleString()}</code>
              </section>
            </div>
          ) : (
            <div className="tab-empty">
              <ListTree size={20} />
              <strong>{activeTab}</strong>
              <span>No additional entities in the current local context.</span>
            </div>
          )}
        </div>
      ) : (
        <div className="event-feed">
          <div className="feed-intro">
            <Braces size={18} />
            <p>Select an entity to inspect code, relationships, evidence, and provenance.</p>
          </div>
          <h3><Clock3 size={12} /> Recent analysis events</h3>
          {[...events].reverse().slice(0, 10).map((event) => (
            <div className="event-row" key={event.id}>
              <span className={`event-marker event-${event.kind.split('.')[0]}`} />
              <div><strong>{event.kind}</strong><small>{new Date(event.created_at).toLocaleTimeString()}</small></div>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
