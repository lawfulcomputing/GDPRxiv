class PDFFileExtensionSpecification():
    def is_satisfied_by(self, cand): # cand = filename
        cand = cand.lower()
        return cand.endswith('.pdf') is True
