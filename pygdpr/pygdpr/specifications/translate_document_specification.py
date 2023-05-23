class TranslateDocumentSpecification():
    def __init__(self, docs):
        self.docs = docs
    def is_satisfied_by(self, doc):
        return (len(self.docs) == 0 or doc in self.docs)
