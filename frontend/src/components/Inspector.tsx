import { useEffect, useMemo, useState } from 'react'
import {
  Braces,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  GitCommitHorizontal,
  ListTree,
  ShieldAlert,
} from 'lucide-react'

import { useCairnStore } from '../store'

const tabs = ['Overview', 'Evidence', 'Relations', 'Raw']
const evidenceKinds = new Set(['Evidence', 'Observation', 'Trace'])

export function Inspector() {
  const [activeTab, setActiveTab] = useState('Overview')
  const nodes = useCairnStore((state) => state.nodes)
  const edges = useCairnStore((state) => state.edges)
  const selectedNodeId = useCairnStore((state) => state.selectedNodeId)
  const events = useCairnStore((state) => state.events)
  const selectNode = useCairnStore((state) => state.selectNode)
  const node = nodes.find((item) => item.id === selectedNodeId) ?? null
  const isHypothesis = node?.kind === 'Hypothesis'

  useEffect(() => setActiveTab('Overview'), [selectedNodeId])

  const connectedEdges = useMemo(
    () => node ? edges.filter((edge) => edge.source_node_id === node.id || edge.target_node_id === node.id) : [],
    [edges, node],
  )
  const connectedNodes = useMemo(() => connectedEdges.flatMap((edge) => {
    const relatedId = edge.source_node_id === node?.id ? edge.target_node_id : edge.source_node_id
    const related = nodes.find((item) => item.id === relatedId)
    return related ? [{ edge, node: related }] : []
  }), [connectedEdges, node, nodes])
  const evidenceNodes = connectedNodes.filter(({ node: related }) => evidenceKinds.has(related.kind))

  const relations = useMemo(() => {
    if (!node) return { supporting: 0, contradicting: 0, related: 0 }
    return {
      supporting: connectedEdges.filter((edge) => edge.kind === 'supports').length,
      contradicting: connectedEdges.filter((edge) => edge.kind === 'contradicts').length,
      related: connectedEdges.length,
    }
  }, [connectedEdges, node])

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

          {activeTab === 'Overview' ? (
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
          ) : activeTab === 'Evidence' ? (
            <div className="inspector-list">
              {evidenceNodes.length ? evidenceNodes.map(({ edge, node: related }) => (
                <button key={edge.id} className="inspector-entity-row" onClick={() => selectNode(related.id)}>
                  <span className={`entity-kind kind-${related.kind.toLowerCase()}`}>{related.kind}</span>
                  <strong>{related.label}</strong>
                  <small>{edge.kind.replaceAll('_', ' ')} · {Math.round(related.confidence * 100)}% confidence</small>
                </button>
              )) : <div className="inspector-empty"><ListTree size={18} /><span>No evidence is directly linked to this node.</span></div>}
            </div>
          ) : activeTab === 'Relations' ? (
            <div className="inspector-list">
              {connectedNodes.length ? connectedNodes.map(({ edge, node: related }) => (
                <button key={edge.id} className="inspector-entity-row" onClick={() => selectNode(related.id)}>
                  <span className="entity-kind">{edge.kind.replaceAll('_', ' ')}</span>
                  <strong>{related.label}</strong>
                  <small>{related.kind} · {related.status}</small>
                </button>
              )) : <div className="inspector-empty"><ListTree size={18} /><span>No linked entities.</span></div>}
            </div>
          ) : (
            <div className="inspector-raw">
              <div className="raw-identity"><span>Canonical key</span><code>{node.entity_key}</code></div>
              <pre>{JSON.stringify({
                graph_type: node.graph_type,
                kind: node.kind,
                status: node.status,
                confidence: node.confidence,
                properties: node.properties,
                created_by: node.created_by,
                created_at: node.created_at,
              }, null, 2)}</pre>
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
