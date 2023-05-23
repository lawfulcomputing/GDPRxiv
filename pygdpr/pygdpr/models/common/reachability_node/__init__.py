from enum import Enum

class Color(Enum):
    WHITE = 'white'
    GREY = 'lightgrey'
    BLACK = 'black'

class ReachabilityNode(object):
    def __init__(self, key=None):
        self.key = key
        self.parent = None
        self.children = []
        self.color = Color.WHITE

    def get_color(self):
        return self.color

    def get_children(self):
        return self.children

    def set_color(self, color):
        self.color = color

    def set_parent(self, parent):
        self.parent = parent

    def add_child(self, child):
        child.set_parent(self)
        self.children.append(child)

class GDPRNode(ReachabilityNode):
    def __init__(self, key):
        key = 'GDPR'
        super().__init__(key)

class DPANode(ReachabilityNode):
    def __init__(self, key, dpa):
        # satellite data
        self.dpa = dpa
        super().__init__(key)

class SourceNode(ReachabilityNode):
    def __init__(self, key, source):
        # satellite data
        self.source = source
        super().__init__(key)

class LabelNode(ReachabilityNode):
    def __init__(self, key, label):
        # satellite data
        self.label = label
        super().__init__(key)

class XPathNode(ReachabilityNode):
    def __init__(self, key, xpath):
        # satellite data
        self.xpath = xpath
        super().__init__(key)
