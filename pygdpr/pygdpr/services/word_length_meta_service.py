from pygdpr.services.metadata_service import MetadataService
import nltk

class WordLengthMetaService(MetadataService):
    def for_text(self, text):
        return len(nltk.word_tokenize(text))
