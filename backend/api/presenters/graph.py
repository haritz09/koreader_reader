"""Presenters for the knowledge graph API."""

from api.schemas.graph import GraphEdgeResponse, GraphNodeResponse, GraphResponse
from core.domain.entities.graph import BookGraph, GraphEdge, GraphNode


def graph_response(graph: BookGraph) -> GraphResponse:
	return GraphResponse(
		book_id=graph.book_id,
		position=graph.position,
		revision=graph.revision,
		nodes=[_node_response(node) for node in graph.nodes],
		edges=[_edge_response(edge) for edge in graph.edges],
	)


def _node_response(node: GraphNode) -> GraphNodeResponse:
	return GraphNodeResponse(
		node_id=node.node_id,
		label=node.label,
		node_type=node.node_type,
		first_seen_position=node.first_seen_position,
		mention_count=node.mention_count,
		description=node.description,
		sub_type=node.sub_type,
		aliases=list(node.aliases),
		importance=node.importance,
	)


def _edge_response(edge: GraphEdge) -> GraphEdgeResponse:
	return GraphEdgeResponse(
		edge_id=edge.edge_id,
		source_id=edge.source_id,
		target_id=edge.target_id,
		statement=edge.statement,
		position=edge.position,
		chunk_id=edge.chunk_id,
	)
