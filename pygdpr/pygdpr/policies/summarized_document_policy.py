import nltk

class SummarizedDocumentPolicy():
    n_sentences = 4
    def is_allowed(self, document_text):
        return nltk.sent_tokenize(document_text) <= self.n_sentences
