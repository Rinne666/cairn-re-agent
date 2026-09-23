import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { CSSProperties } from 'react'
import {
  Activity,
  Braces,
  Check,
  CircleHelp,
  FileSearch,
  Quote,
} from 'lucide-react'

import type { GraphNodeData } from '../types'

interface NodeMetrics {
  incoming: number
  outgoing: number
  evidence: number
  hypotheses: number
  contradictions: number
}

export function GraphCard({ data, selected }: NodeProps) {
  const node = data.node as GraphNodeData
  const metrics = data.metrics as NodeMetrics
  const motionOrder = Number(data.motionOrder ?? 0)
  const address = typeof node.properties.address === 'string' ? node.properties.address : null
  const classes = `graph-card kind-${node.kind.toLowerCase()} node-motion-${motionOrder} ${selected ? 'is-selected' : ''}`

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
          <span>{String(node.properties.size ?? '312 bytes')}</span>
        </div>
        <div className="function-metrics">
          <span>{metrics.incoming} callers</span>
          <span>{metrics.outgoing} callees</span>
          <span>{metrics.evidence} evidence</span>
          <span>{metrics.hypotheses} hypotheses</span>
        </div>
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  if (node.kind === 'Hypothesis') {
    const support = Number(node.properties.supporting_evidence ?? metrics.evidence ?? 0)
    const conflicts = Number(node.properties.contradictions ?? metrics.contradictions ?? 0)
    return (
      <div className={classes} style={{ '--motion-order': motionOrder } as CSSProperties}>
        <Handle type="target" position={Position.Left} />
        <div className="hypothesis-title"><CircleHelp size={14} /><strong>{node.label}</strong></div>
        <div className="confidence-row"><span>confidence</span><b>{Math.round(node.confidence * 100)}%</b></div>
        <div className="hypothesis-evidence"><span>+{support} evidence</span><span>-{conflicts} conflict</span></div>
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
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
