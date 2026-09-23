import type { GraphEdgeData, GraphNodeData, WorkspaceSection } from '../types'

export type GraphMode = 'summary' | 'analysis'
export type ExpansionKind = 'callers' | 'callees' | 'dataflow' | 'evidence' | 'xrefs' | 'path'

export interface NodeMetrics {
  incoming: number
  outgoing: number
  evidence: number
  hypotheses: number
  contradictions: number
}

export const SUMMARY_FUNCTION_LIMIT = 6
export const ANALYSIS_NODE_LIMIT = 36

const semanticKinds = new Set(['Function', 'Hypothesis', 'Fact', 'Conclusion', 'Intent'])
const evidenceKinds = new Set(['Evidence', 'Observation', 'Trace'])
const relationKinds: Record<ExpansionKind, Set<string>> = {
  callers: new Set(['calls']),
  callees: new Set(['calls']),
  dataflow: new Set(['flows_to']),
  evidence: new Set(['supports', 'contradicts', 'derived_from']),
  xrefs: new Set(['references']),
  path: new Set(['calls', 'flows_to']),
}

export function projectSummary(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  section: WorkspaceSection,
  expandFunctionCluster: boolean,
): GraphNodeData[] {
  let candidates = nodes.filter((node) => {
    if (node.kind === 'Fact') return isConfirmedFact(node)
    if (node.kind === 'Intent') return ['open', 'claimed', 'running'].includes(node.status)
    return semanticKinds.has(node.kind)
  })
  if (section === 'program') candidates = candidates.filter((node) => node.kind === 'Function')
  if (section === 'hypotheses') candidates = candidates.filter((node) => node.kind === 'Hypothesis')

  const functions = candidates.filter((node) => node.kind === 'Function')
  const rankedFunctions = [...functions].sort((left, right) =>
    functionValue(right, edges) - functionValue(left, edges) || left.label.localeCompare(right.label),
  )
  const keptFunctions = expandFunctionCluster
    ? rankedFunctions
    : rankedFunctions.slice(0, SUMMARY_FUNCTION_LIMIT)
  const otherSemanticNodes = candidates.filter((node) => node.kind !== 'Function')
  const result = [...otherSemanticNodes, ...keptFunctions]

  const overflow = rankedFunctions.slice(SUMMARY_FUNCTION_LIMIT)
  if (overflow.length && !expandFunctionCluster) {
    result.push(makeFunctionCluster(overflow))
  }

  return result.sort((left, right) => {
    const lane = (node: GraphNodeData) => node.kind === 'Function' || node.kind === 'FunctionCluster'
      ? 0
      : node.kind === 'Fact' || node.kind === 'Intent' ? 1 : 2
    return lane(left) - lane(right) || left.created_at.localeCompare(right.created_at)
  })
}

export function projectSummaryEdges(
  visibleNodes: GraphNodeData[],
  allEdges: GraphEdgeData[],
): GraphEdgeData[] {
  const visibleIds = new Set(visibleNodes.map((node) => node.id))
  const result = allEdges.filter((edge) => visibleIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id))
  const cluster = visibleNodes.find((node) => node.kind === 'FunctionCluster')
  if (!cluster) return result

  const memberIds = new Set((cluster.properties.member_ids as string[] | undefined) ?? [])
  const relatedIds = new Set<string>()
  for (const edge of allEdges) {
    if (memberIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id)) relatedIds.add(edge.target_node_id)
    if (memberIds.has(edge.target_node_id) && visibleIds.has(edge.source_node_id)) relatedIds.add(edge.source_node_id)
  }
  for (const relatedId of relatedIds) {
    result.push({
      id: `projection:${cluster.id}:${relatedId}`,
      project_id: cluster.project_id,
      source_node_id: cluster.id,
      target_node_id: relatedId,
      kind: 'related',
      properties: { summary: true },
      created_by: 'graph-projection',
      created_at: cluster.created_at,
    })
  }
  return result
}

export function isConfirmedFact(node: GraphNodeData): boolean {
  return node.kind === 'Fact' && (node.confidence >= 0.9 || ['confirmed', 'completed'].includes(node.status))
}

function functionValue(node: GraphNodeData, edges: GraphEdgeData[]): number {
  return edges.reduce((score, edge) => {
    if (edge.source_node_id !== node.id && edge.target_node_id !== node.id) return score
    if (edge.kind === 'supports' || edge.kind === 'contradicts' || edge.kind === 'derived_from') return score + 4
    if (edge.kind === 'calls' || edge.kind === 'flows_to') return score + 3
    return score + 1
  }, node.confidence)
}

function makeFunctionCluster(members: GraphNodeData[]): GraphNodeData {
  const first = members[0]
  return {
    id: 'projection:function-cluster',
    project_id: first.project_id,
    binary_id: null,
    graph_type: 'program',
    kind: 'FunctionCluster',
    label: `${members.length} related functions`,
    entity_key: 'projection:function-cluster',
    properties: { member_ids: members.map((node) => node.id), count: members.length },
    confidence: 1,
    status: 'collapsed',
    created_by: 'graph-projection',
    created_at: first.created_at,
  }
}

export function projectAnalysis(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  rootId: string | null,
  expansions: Set<ExpansionKind>,
  depth = 1,
): { nodes: GraphNodeData[]; edges: GraphEdgeData[] } {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  if (!rootId || !byId.has(rootId)) return { nodes: [], edges: [] }

  const visibleIds = new Set([rootId])
  const visibleEdges = new Map<string, GraphEdgeData>()
  let frontier = new Set([rootId])
  const maxDepth = Math.max(1, Math.min(depth, 2))

  for (let hop = 0; hop < maxDepth && frontier.size; hop += 1) {
    const next = new Set<string>()
    for (const edge of edges) {
      const step = expansionForEdge(edge, expansions, frontier)
      if (!step) continue
      visibleEdges.set(edge.id, edge)
      for (const id of [edge.source_node_id, edge.target_node_id]) {
        if (byId.has(id) && !visibleIds.has(id) && visibleIds.size < ANALYSIS_NODE_LIMIT) {
          visibleIds.add(id)
          next.add(id)
        }
      }
    }
    frontier = next
  }

  return {
    nodes: nodes.filter((node) => visibleIds.has(node.id)),
    edges: [...visibleEdges.values()].filter(
      (edge) => visibleIds.has(edge.source_node_id) && visibleIds.has(edge.target_node_id),
    ),
  }
}

function expansionForEdge(
  edge: GraphEdgeData,
  expansions: Set<ExpansionKind>,
  frontier: Set<string>,
): ExpansionKind | null {
  if (expansions.has('callers') && edge.kind === 'calls' && frontier.has(edge.target_node_id)) return 'callers'
  if (expansions.has('callees') && edge.kind === 'calls' && frontier.has(edge.source_node_id)) return 'callees'
  for (const kind of expansions) {
    if (kind === 'callers' || kind === 'callees') continue
    if (relationKinds[kind].has(edge.kind) && (frontier.has(edge.source_node_id) || frontier.has(edge.target_node_id))) {
      return kind
    }
  }
  return null
}

export function getNodeMetrics(node: GraphNodeData, nodes: GraphNodeData[], edges: GraphEdgeData[]): NodeMetrics {
  const nodeById = new Map(nodes.map((item) => [item.id, item]))
  let evidence = 0
  let contradictions = 0
  let incoming = 0
  let outgoing = 0
  let hypotheses = 0

  for (const edge of edges) {
    if (edge.target_node_id === node.id) incoming += 1
    if (edge.source_node_id === node.id) outgoing += 1
    if (edge.kind === 'supports' && edge.source_node_id === node.id) hypotheses += 1
    if (!['supports', 'contradicts', 'derived_from'].includes(edge.kind)) continue
    const neighborId = edge.source_node_id === node.id ? edge.target_node_id : edge.target_node_id === node.id ? edge.source_node_id : null
    const neighbor = neighborId ? nodeById.get(neighborId) : null
    if (!neighbor || !evidenceKinds.has(neighbor.kind)) continue
    if (edge.kind === 'contradicts') contradictions += 1
    else evidence += 1
  }

  return { incoming, outgoing, evidence, hypotheses, contradictions }
}
