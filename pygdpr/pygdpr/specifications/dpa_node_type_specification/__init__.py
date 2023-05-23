class DPANodeTypeSpecification:
    def is_satisfied_by(self, dpa_node):
        classname = dpa_node.__class__.__name__
        return (classname == 'DPANode')
