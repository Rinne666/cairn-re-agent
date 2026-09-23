import { useEffect, useMemo, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  GitBranch,
  Maximize2,
  Route,
  ScanLine,
  ShieldCheck,
  Waypoints,
} from 'lucide-react'
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from '@xyflow/react'

import { useCairnStore } from '../store'
import type { GraphEdgeData, GraphNodeData, GraphType } from '../types'
import { GraphCard } from './GraphCard'

const nodeTypes = { graphCard: GraphCard }

const edgeStyles: Record<string, { stroke: string; width: number; dash?: string }> = {
  calls: { stroke: '#74a48d', width: 1.35 },
  flows_to: { stroke: '#568c73', width: 1.9 },
  supports: { stroke: '#a6b88f', width: 1.25, dash: '5 5' },
  contradicts: { stroke: '#c98983', width: 1.3, dash: '2 5' },
  derived_from: { stroke: '#91afa0', width: 1, dash: '4 5' },
  motivates: { stroke: '#af9a68', width: 1, dash: '2 5' },
  produced: { stroke: '#af9a68', width: 1, dash: '3 5' },
  references: { stroke: '#abc0b5', width: 1 },
}

function laneFor(node: GraphNodeData, view: GraphType): number {
  if (view === 'exploration') return node.kind === 'Fact' ? 0 : node.kind === 'Intent' ? 1 : 2
  if (view === 'evidence') {
    return ['Observation', 'Evidence', 'Trace'].includes(node.kind) ? 0 : node.kind === 'Hypothesis' ? 1 : 2
  }
  return node.kind === 'Function' ? 0 : ['String', 'Constant', 'API'].includes(node.kind) ? 1 : 2
}

function layoutNodes(
  items: GraphNodeData[],
  edges: GraphEdgeData[],
  view: GraphType,
): Node[] {
  const laneCounts = new Map<number, number>()
  const incoming = new Map<string, number>()
  const outgoing = new Map<string, number>()
  edges.forEach((edge) => {
    incoming.set(edge.target_node_id, (incoming.get(edge.target_node_id) ?? 0) + 1)
    outgoing.set(edge.source_node_id, (outgoing.get(edge.source_node_id) ?? 0) + 1)
  })
  return items.map((item) => {
    const lane = laneFor(item, view)
    const row = laneCounts.get(lane) ?? 0
    laneCounts.set(lane, row + 1)
    const isCompact = !['Function', 'Hypothesis'].includes(item.kind)
    return {
      id: item.id,
      type: 'graphCard',
      data: {
        node: item,
        motionOrder: row + lane * 2,
        metrics: {
          incoming: incoming.get(item.id) ?? 0,
          outgoing: outgoing.get(item.id) ?? 0,
          evidence: edges.filter((edge) => edge.target_node_id === item.id && edge.kind === 'supports').length,
          hypotheses: edges.filter((edge) => edge.source_node_id === item.id && edge.kind === 'supports').length,
          contradictions: edges.filter((edge) => edge.target_node_id === item.id && edge.kind === 'contradicts').length,
        },
      },
      position: {
        x: lane * 310 + (row % 2) * 18,
        y: row * (isCompact ? 116 : 146) + (lane % 2) * 42,
      },
    }
  })
}

function localContext(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  selectedNodeId: string | null,
  depth: number,
): GraphNodeData[] {
  if (!nodes.length) return []
  const validIds = new Set(nodes.map((node) => node.id))
  const anchor = selectedNodeId && validIds.has(selectedNodeId)
    ? selectedNodeId
    : nodes.find((node) => node.kind === 'Function' || node.kind === 'Hypothesis' || node.kind === 'Fact')?.id
  if (!anchor) return nodes.slice(0, 8)
  const visible = new Set([anchor])
  let frontier = new Set([anchor])
  for (let hop = 0; hop < depth; hop += 1) {
    const next = new Set<string>()
    edges.forEach((edge) => {
      if (frontier.has(edge.source_node_id) && validIds.has(edge.target_node_id)) next.add(edge.target_node_id)
      if (frontier.has(edge.target_node_id) && validIds.has(edge.source_node_id)) next.add(edge.source_node_id)
    })
    next.forEach((id) => visible.add(id))
    frontier = next
  }
  if (visible.size === 1) nodes.slice(0, 4).forEach((node) => visible.add(node.id))
  return nodes.filter((node) => visible.has(node.id)).slice(0, 14)
}

export function GraphCanvas() {
  const [contextDepth, setContextDepth] = useState(1)
  const allNodes = useCairnStore((state) => state.nodes)
  const allEdges = useCairnStore((state) => state.edges)
  const view = useCairnStore((state) => state.view)
  const section = useCairnStore((state) => state.section)
  const selectedNodeId = useCairnStore((state) => state.selectedNodeId)
  const selectNode = useCairnStore((state) => state.selectNode)

  useEffect(() => setContextDepth(1), [view, selectedNodeId])

  const scopedNodes = useMemo(() => {
    const graphNodes = allNodes.filter((node) => node.graph_type === view)
    if (section === 'hypotheses') return graphNodes.filter((node) => node.kind === 'Hypothesis')
    if (section === 'evidence') return graphNodes.filter((node) => node.kind !== 'Hypothesis')
    return graphNodes
  }, [allNodes, section, view])
  const visible = useMemo(
    () => localContext(scopedNodes, allEdges, selectedNodeId, contextDepth),
    [allEdges, contextDepth, scopedNodes, selectedNodeId],
  )
  const visibleIds = useMemo(() => new Set(visible.map((node) => node.id)), [visible])
  const visibleEdges = useMemo(
    () => allEdges.filter((edge) => visibleIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id)),
    [allEdges, visibleIds],
  )
  const flowNodes = useMemo(() => layoutNodes(visible, allEdges, view), [allEdges, visible, view])
  const flowEdges = useMemo<Edge[]>(
    () => visibleEdges.map((edge) => {
      const semantic = edgeStyles[edge.kind] ?? { stroke: '#abc0b5', width: 1 }
      return {
        id: edge.id,
        source: edge.source_node_id,
        target: edge.target_node_id,
        label: edge.kind.replaceAll('_', ' '),
        type: 'smoothstep',
        markerEnd: ['calls', 'flows_to'].includes(edge.kind)
          ? { type: MarkerType.ArrowClosed, color: semantic.stroke, width: 12, height: 12 }
          : undefined,
        style: { stroke: semantic.stroke, strokeWidth: semantic.width, strokeDasharray: semantic.dash },
        labelStyle: { fill: '#6f8178', fontSize: 9, fontFamily: 'var(--mono)' },
        labelBgStyle: { fill: '#f7faf8', fillOpacity: 0.96 },
      }
    }),
    [visibleEdges],
  )
  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges)

  useEffect(() => setNodes(flowNodes), [flowNodes, setNodes])
  useEffect(() => setEdges(flowEdges), [flowEdges, setEdges])

  const title = section === 'hypotheses' ? 'Hypothesis context' : section === 'evidence' ? 'Evidence context' : `${view} graph`

  return (
    <section className="graph-stage" aria-label={title}>
      <div className="graph-toolbar">
        <div className="graph-title">
          <GitBranch size={14} />
          <strong>{title}</strong>
          <span>{visible.length} nodes · {visibleEdges.length} relations</span>
        </div>
        <div className="context-actions" aria-label="Graph expansion controls">
          <button onClick={() => setContextDepth(2)}><ChevronLeft size={12} /> Callers</button>
          <button onClick={() => setContextDepth(2)}>Callees <ChevronRight size={12} /></button>
          <button onClick={() => setContextDepth(2)}><Waypoints size={12} /> Dataflow</button>
          <button onClick={() => setContextDepth(2)}><ShieldCheck size={12} /> Evidence</button>
          <button onClick={() => setContextDepth(3)}><Route size={12} /> Path</button>
          <button className="icon-only" onClick={() => setContextDepth(3)} title="Overview mode"><Maximize2 size={12} /></button>
        </div>
      </div>
      {nodes.length === 0 ? (
        <div className="empty-graph">
          <ScanLine size={24} />
          <strong>No entities in this context</strong>
          <span>Select another workspace section or run a worker.</span>
        </div>
      ) : (
        <ReactFlow
          key={`${view}-${section}-${contextDepth}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => selectNode(node.id)}
          onPaneClick={() => selectNode(null)}
          fitView
          fitViewOptions={{ padding: 0.32 }}
          minZoom={0.4}
          maxZoom={1.5}
          colorMode="light"
        >
          <Background variant={BackgroundVariant.Dots} color="#c9dcd2" gap={24} size={1} />
          <Controls showInteractive={false} />
          <MiniMap nodeColor="#7aa991" maskColor="rgba(247,250,248,.76)" pannable zoomable />
        </ReactFlow>
      )}
    </section>
  )
}
