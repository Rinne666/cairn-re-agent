import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ChevronDown,
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
import type { GraphEdgeData, GraphNodeData, WorkspaceSection } from '../types'
import {
  getNodeMetrics,
  projectAnalysis,
  projectSummary,
  projectSummaryEdges,
  type ExpansionKind,
  type GraphMode,
  type NodeMetrics,
} from './graphProjection'
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
  related: { stroke: '#cbb77f', width: 1.1, dash: '4 4' },
}

interface GraphCardPayload extends Record<string, unknown> {
  node: GraphNodeData
  metrics: NodeMetrics
  motionOrder: number
  isCluster?: boolean
  onExpandEvidence?: () => void
  onToggleCluster?: () => void
}

type FlowNode = Node<GraphCardPayload, 'graphCard'>

function laneFor(node: GraphNodeData): number {
  if (node.kind === 'Function' || node.kind === 'FunctionCluster') return 0
  if (node.kind === 'Fact' || node.kind === 'Intent' || node.kind === 'Evidence' || node.kind === 'Observation') return 1
  return 2
}

function layoutNodes(
  items: GraphNodeData[],
  allNodes: GraphNodeData[],
  edges: GraphEdgeData[],
  compactLayout: boolean,
  onExpandEvidence: (nodeId: string) => void,
  onToggleCluster: () => void,
): FlowNode[] {
  const laneCounts = new Map<number, number>()
  return items.map((item, index) => {
    const lane = laneFor(item)
    const row = laneCounts.get(lane) ?? 0
    laneCounts.set(lane, row + 1)
    const isCluster = item.kind === 'FunctionCluster'
    return {
      id: item.id,
      type: 'graphCard',
      data: {
        node: item,
        metrics: isCluster ? { incoming: 0, outgoing: 0, evidence: 0, hypotheses: 0, contradictions: 0 } : getNodeMetrics(item, allNodes, edges),
        motionOrder: row + lane * 2,
        isCluster,
        onExpandEvidence: () => onExpandEvidence(item.id),
        onToggleCluster,
      },
      position: compactLayout
        ? { x: 0, y: index * 150 }
        : {
            x: lane * 318 + (row % 2) * 16,
            y: row * (['Function', 'Hypothesis', 'FunctionCluster'].includes(item.kind) ? 142 : 112) + (lane % 2) * 34,
          },
    }
  })
}

const expansionControls: Array<{ id: ExpansionKind; label: string; icon?: typeof ChevronRight }> = [
  { id: 'callers', label: 'Callers', icon: ChevronDown },
  { id: 'callees', label: 'Callees', icon: ChevronRight },
  { id: 'dataflow', label: 'Dataflow', icon: Waypoints },
  { id: 'evidence', label: 'Evidence', icon: ShieldCheck },
  { id: 'xrefs', label: 'Xrefs', icon: GitBranch },
]

function titleFor(section: WorkspaceSection, mode: GraphMode): string {
  if (mode === 'summary') return section === 'program' ? 'Key functions' : 'Case summary'
  if (section === 'hypotheses') return 'Hypothesis analysis'
  return 'Local analysis'
}

export function GraphCanvas() {
  const [compactLayout, setCompactLayout] = useState(() => window.innerWidth <= 1100)
  const [mode, setMode] = useState<GraphMode>('summary')
  const [expansions, setExpansions] = useState<Set<ExpansionKind>>(new Set())
  const [pathDepth, setPathDepth] = useState(1)
  const [functionClusterExpanded, setFunctionClusterExpanded] = useState(false)
  const allNodes = useCairnStore((state) => state.nodes)
  const allEdges = useCairnStore((state) => state.edges)
  const section = useCairnStore((state) => state.section)
  const selectedNodeId = useCairnStore((state) => state.selectedNodeId)
  const selectNode = useCairnStore((state) => state.selectNode)

  useEffect(() => {
    const updateLayout = () => setCompactLayout(window.innerWidth <= 1100)
    window.addEventListener('resize', updateLayout)
    return () => window.removeEventListener('resize', updateLayout)
  }, [])

  useEffect(() => {
    setMode('summary')
    setExpansions(new Set())
    setPathDepth(1)
    setFunctionClusterExpanded(false)
  }, [section])

  const summaryNodes = useMemo(
    () => projectSummary(allNodes, allEdges, section, functionClusterExpanded),
    [allEdges, allNodes, functionClusterExpanded, section],
  )
  const rootId = selectedNodeId && allNodes.some((node) => node.id === selectedNodeId)
    ? selectedNodeId
    : summaryNodes.find((node) => node.kind !== 'FunctionCluster')?.id ?? null
  const analysis = useMemo(
    () => projectAnalysis(allNodes, allEdges, rootId, expansions, pathDepth),
    [allEdges, allNodes, expansions, pathDepth, rootId],
  )
  const visible = mode === 'summary' ? summaryNodes : analysis.nodes
  const visibleEdges = useMemo(
    () => mode === 'summary'
      ? projectSummaryEdges(visible, allEdges)
      : analysis.edges,
    [allEdges, analysis.edges, mode, visible],
  )

  const onExpandEvidence = useCallback((nodeId: string) => {
    selectNode(nodeId)
    setMode('analysis')
    setExpansions(new Set(['evidence']))
  }, [selectNode])
  const onToggleCluster = useCallback(() => setFunctionClusterExpanded((value) => !value), [])
  const flowNodes = useMemo(
    () => layoutNodes(visible, allNodes, allEdges, compactLayout, onExpandEvidence, onToggleCluster),
    [allEdges, allNodes, compactLayout, onExpandEvidence, onToggleCluster, visible],
  )
  const flowEdges = useMemo<Edge[]>(() => visibleEdges.map((edge) => {
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
  }), [visibleEdges])

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(flowEdges)
  useEffect(() => setNodes(flowNodes), [flowNodes, setNodes])
  useEffect(() => setEdges(flowEdges), [flowEdges, setEdges])

  const enterAnalysis = () => {
    if (!selectedNodeId && rootId) selectNode(rootId)
    setMode('analysis')
  }
  const showSummary = () => {
    setExpansions(new Set())
    setPathDepth(1)
    setMode('summary')
  }
  const toggleExpansion = (kind: ExpansionKind) => {
    enterAnalysis()
    setExpansions((current) => {
      const next = new Set(current)
      if (next.has(kind)) next.delete(kind)
      else next.add(kind)
      return next
    })
  }
  const title = titleFor(section, mode)

  return (
    <section className="graph-stage" aria-label={title}>
      <div className="graph-toolbar">
        <div className="graph-title">
          <GitBranch size={14} />
          <strong>{title}</strong>
          <span>{visible.length} nodes · {visibleEdges.length} relations</span>
        </div>
        <div className="graph-mode-switch" role="group" aria-label="Graph detail level">
          <button className={mode === 'summary' ? 'active' : ''} onClick={showSummary}>Summary</button>
          <button className={mode === 'analysis' ? 'active' : ''} onClick={enterAnalysis}>Analysis</button>
        </div>
        <div className="context-actions" aria-label="Expand graph context">
          {expansionControls.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={expansions.has(id) ? 'active' : ''}
              onClick={() => toggleExpansion(id)}
              disabled={!rootId}
              aria-pressed={expansions.has(id)}
            >
              {Icon ? <Icon size={12} /> : null}{label}
            </button>
          ))}
          <button
            className={`path-control ${pathDepth > 1 ? 'active' : ''}`}
            onClick={() => {
              enterAnalysis()
              const expand = pathDepth === 1
              setPathDepth(expand ? 2 : 1)
              setExpansions((current) => {
                const next = new Set(current)
                if (expand) next.add('path')
                else next.delete('path')
                return next
              })
            }}
            disabled={!rootId}
            aria-pressed={pathDepth > 1}
          >
            <Route size={12} /> Path
          </button>
          {functionClusterExpanded ? (
            <button className="icon-only" onClick={onToggleCluster} title="Collapse related functions">
              <Maximize2 size={12} />
            </button>
          ) : null}
        </div>
      </div>
      {nodes.length === 0 ? (
        <div className="empty-graph">
          <ScanLine size={24} />
          <strong>No entities in this context</strong>
          <span>{mode === 'analysis' ? 'Select a node, then expand one relation at a time.' : 'No high-value entities are available in this view yet.'}</span>
        </div>
      ) : (
        <ReactFlow
          key={`${compactLayout}-${mode}-${visible.map((node) => node.id).join('|')}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => {
            const payload = node.data as GraphCardPayload
            if (payload.isCluster) {
              onToggleCluster()
              return
            }
            selectNode(payload.node.id)
          }}
          onPaneClick={() => selectNode(null)}
          fitView
          fitViewOptions={{ padding: { top: 88, right: 32, bottom: 32, left: 32 } }}
          minZoom={0.4}
          maxZoom={1.5}
          colorMode="light"
        >
          <Background variant={BackgroundVariant.Dots} color="#c9dcd2" gap={24} size={1} />
          <Controls showInteractive={false} />
          <MiniMap nodeColor={(node) => (node.data as GraphCardPayload).isCluster ? '#d2a85e' : '#7aa991'} maskColor="rgba(247,250,248,.76)" pannable zoomable />
        </ReactFlow>
      )}
    </section>
  )
}
