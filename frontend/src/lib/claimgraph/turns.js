/*
 * An investigation grows in turns: the initial run, then one
 * follow-up per open question a person chose to research.
 * A turn's overlay says which nodes and edges it added, so the
 * graph can show "only what this follow-up found".
 */
export function turnOverlay(graph, turn) {
  if (!turn) return null;

  const followups = graph.followups ?? [];

  if (turn === "initial") {
    if (followups.some((item) => !item.delta)) return null;

    const laterNodes = new Set(followups.flatMap((f) => f.delta.added_node_ids ?? []));
    const laterEdges = new Set(followups.flatMap((f) => f.delta.added_edge_ids ?? []));

    return {
      added_node_ids: graph.nodes
        .filter((node) => !laterNodes.has(node.node_id))
        .map((node) => node.node_id),
      added_edge_ids: graph.edges
        .filter((edge) => !laterEdges.has(edge.edge_id))
        .map((edge) => edge.edge_id),
      reassessed_hypothesis_ids: [],
    };
  }

  return followups.find((item) => item.run_id === turn)?.delta ?? null;
}
