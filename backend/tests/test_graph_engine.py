def test_seed_graph_has_expected_nodes_and_edges(fresh_state):
    graph = fresh_state.graph
    assert set(graph.nodes.keys()) == {"FL1", "TR1", "HT1", "AC1", "AC2", "TR2", "FL2"}
    assert len(graph.edges) == 6


def test_successors_and_predecessors_reflect_edges(fresh_state):
    graph = fresh_state.graph

    fl1_successors = [e.target for e in graph.successors("FL1")]
    assert fl1_successors == ["TR1"]

    ht1_predecessors = [e.source for e in graph.predecessors("HT1")]
    assert ht1_predecessors == ["TR1"]

    # a node with no outgoing edges has an empty successor list, not an error
    assert graph.successors("FL2") == []


def test_topological_order_from_includes_every_reachable_node(fresh_state):
    graph = fresh_state.graph
    order = graph.topological_order_from("FL1")

    assert order[0] == "FL1"
    assert set(order) == {"FL1", "TR1", "HT1", "AC1", "AC2", "TR2", "FL2"}

    # every node must appear after all of its predecessors
    position = {node_id: i for i, node_id in enumerate(order)}
    for edge in graph.edges:
        assert position[edge.source] < position[edge.target]


def test_topological_order_from_leaf_is_just_itself(fresh_state):
    graph = fresh_state.graph
    assert graph.topological_order_from("FL2") == ["FL2"]
