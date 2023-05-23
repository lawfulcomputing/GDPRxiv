from pygdpr.services.metadata_service import MetadataService

class CharLengthMetaService(MetadataService):
    def for_text(self, text):
        return len(text)
