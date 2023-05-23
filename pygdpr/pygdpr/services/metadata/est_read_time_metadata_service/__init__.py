from pygdpr.services.metadata_service import MetadataService
import nltk

class EstReadTimeMetadataService(MetadataService):
    def for_text(self, text):
        # https://help.medium.com/hc/en-us/articles/214991667-Read-time
        wpm = 265
        words = nltk.word_tokenize(text)
        return len(words) / wpm
