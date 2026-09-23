import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { CSSProperties } from 'react'
import {
  Activity,
  Braces,
  Check,
  CircleHelp,
  FileSearch,
  Layers3,
  Quote,
} from 'lucide-react'

import type { GraphNodeData } from '../types'
import type { NodeMetrics } from './graphProjection'

export function GraphCard({ data, selected }: NodeProps) {
  const node = data.node as GraphNodeData
  const metrics = data.metrics as NodeMetrics
  const motionOrder = Number(data.motionOrder ?? 0)
  const onExpandEvidence = data.onExpandEvidence as (() => void) | undefined
  const address = typeof node.properties.address === 'string' ? node.properties.address : null
  const size = typeof node.properties.size === 'number' || typeof node.properties.size === 'string'
    ? `${node.properties.size} bytes`
    : null
  const classes = `graph-card kind-${node.kind.toLowerCase()} node-motion-${motionOrder} ${selected ? 'is-selected' : ''}`

  if (data.isCluster) {
    const onToggleCluster = data.onToggleCluster as (() => void) | undefined
    return (
      <div className={`${classes} cluster-card`} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <Layers3 size={15} />
        <div><span>COLLAPSED CONTEXT</span><strong>{node.label}</strong></div>
        <button onClick={(event) => { event.stopPropagation(); onToggleCluster?.() }}>Expand</button>
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  if (node.kind === 'Function') {
    return (
      <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <div className="function-title">
          <Braces size={14} />
          <strong>{node.label}</strong>
        </div>
        <div className="function-address">
          <code>{address ?? 'address unknown'}</code>
          {size ? <span>{size}</span> : null}
        </div>
        <div className="function-metrics">
          <span>{metrics.incoming} callers</span>
          <span>{metrics.outgoing} callees</span>
        </div>
        <EvidenceBadges metrics={metrics} onExpand={onExpandEvidence} />
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  if (node.kind === 'Hypothesis') {
    return (
      <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <div className="hypothesis-title"><CircleHelp size={14} /><strong>{node.label}</strong></div>
        <div className="confidence-row"><span>confidence</span><b>{Math.round(node.confidence * 100)}%</b></div>
        <EvidenceBadges metrics={metrics} onExpand={onExpandEvidence} />
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  if (node.kind === 'Intent') {
    return (
      <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <Activity size={13} />
        <div><strong>{node.label}</strong><span>{node.status}</span></div>
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  if (node.kind === 'Evidence' || node.kind === 'Observation') {
    const provenance = node.properties.provenance as Record<string, unknown> | undefined
    return (
      <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <FileSearch size={13} />
        <div>
          <span>{String(provenance?.tool ?? 'worker observation')}</span>
          <strong>{node.label}</strong>
          <code>{node.entity_key.split(':').slice(-1)[0]}</code>
        </div>
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  const isVerified = node.confidence >= 0.9
  return (
    <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
      <Handle type="target" position={Position.Left} />
      {node.kind === 'String' ? <Quote size={13} /> : isVerified ? <Check size={13} /> : <FileSearch size={13} />}
      <div><span>{node.kind}</span><strong>{node.label}</strong></div>
      <EvidenceBadges metrics={metrics} onExpand={onExpandEvidence} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

function EvidenceBadges({ metrics, onExpand }: { metrics: NodeMetrics; onExpand?: () => void }) {
  if (!metrics.evidence && !metrics.contradictions) return null
  return (
    <div className="graph-evidence-badges">
      {metrics.evidence ? (
        <button className="evidence-count" onClick={(event) => { event.stopPropagation(); onExpand?.() }}>
          +{metrics.evidence} evidence
        </button>
      ) : null}
      {metrics.contradictions ? (
        <button className="conflict-count" onClick={(event) => { event.stopPropagation(); onExpand?.() }}>
          −{metrics.contradictions} conflict
        </button>
      ) : null}
    </div>
  )
}
