from pygdpr.services.metadata_service import MetadataService
import nltk

class CitationsCountMetadataService(MetadataService):
    def for_text(self, text):
        count = 0
        targets = ['gdpr', 'rgpd', '2016/679']
        words = nltk.word_tokenize(text)
        words = [w.lower() for w in words]
        for w in words:
            if w in targets:
                count += 1
        return count
