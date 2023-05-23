class RootDocumentSpecification():
    def __init__(self, root):
        self.root = root

    def is_satisfied_by(self, document):
        split = self.root.split('/')
        doc_index = split.index(doc) if document in split else -1
        last_index = len(split) - 1
        return (doc_index == last_index)
