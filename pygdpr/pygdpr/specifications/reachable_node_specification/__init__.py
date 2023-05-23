from pygdpr.models.common.reachability_node import Color

class ReachableNodeSpecification:
    def is_satisfied_by(self, node):
        reachable = True
        children = node.get_children()
        if len(children) == 0:
            return reachable
        colors = set([n.get_color() for n in children])
        if Color.WHITE in colors:
            reachable = False
        return reachable
