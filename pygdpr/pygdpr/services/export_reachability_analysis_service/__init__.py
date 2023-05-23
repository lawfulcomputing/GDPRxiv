from graphviz import Graph
import os

class ExportReachabilityAnalysisService:
    def get_height(self, node):
        h = 0
        while len(node.children) > 0:
            h += 1
            node = node.children[-1]
        return h

    def get_node_color(self, node):
        return node.get_color().value

    def get_node_text_color(self, node):
        text_color = 'black'
        node_color = self.get_node_color(node)
        if node_color == 'black':
            text_color = 'white'
        return text_color

    def get_node_id(self, node):
        node_id = ""
        parent = node.parent
        while parent is not None:
            node_id += parent.key
            parent = parent.parent
        node_id += node.key
        return node_id

    def extend_dot_with_node(self, dot, node):
        node_id = self.get_node_id(node)
        label = node.key
        dot.node(
            node_id,
            label,
            style='filled',
            color=self.get_node_color(node),
            fontcolor=self.get_node_text_color(node)
        )
        return dot

    def extend_dot_with_edge(self, dot, node_a, node_b):
        node_a_id = self.get_node_id(node_a)
        node_b_id = self.get_node_id(node_b)
        dot.edge(node_a_id, node_b_id, constraint='true')
        return dot

    def build_dot(self, node, depth, dot=None):
        assert depth >= 0
        if dot is None:
            dot = Graph(format='svg')
            self.extend_dot_with_node(dot, node)
        if depth == 0:
            return dot
        children = node.get_children()
        for i in range(len(children)):
            child_node = children[i]
            self.extend_dot_with_node(dot, child_node)
            self.extend_dot_with_edge(dot, node, child_node)
            if i == len(children) - 1:
                depth -= 1
            self.build_dot(child_node, depth, dot)
        return dot

    def for_node(self, node, path, depth=None):
        max_depth = self.get_height(node)
        if depth is None:
            depth = max_depth
        assert 0 <= depth <= max_depth
        path = os.path.abspath(path)
        dot = self.build_dot(node, depth)
        dot.render(path, view=False)
        return path
