from pygdpr.services.metadata_service import *
import nltk

class StatisticsMetadataService(MetadataService):
    def size_in_bytes(self, text):
        size_in_bytes = len(text.encode('utf-8'))
        return size_in_bytes

    def char_count(self, text):
        chars = 0
        for c in text:
            if c == " " or c == "\s": continue
            chars += 1
        return chars

    def char_with_spaces_count(self, text):
        return len(text)

    def word_count(self, text):
        return len(nltk.word_tokenize(text))

    def sentence_count(self, text):
        return len(nltk.sent_tokenize(text))

    def paragraph_count(self, text):
        paragraphs = 0
        for c in text:
            if c != "\n": continue
            paragraphs += 1
        return paragraphs

    def page_count(self, text):
        chars_per_page = 3000
        num_chars = len(text)
        return num_chars / chars_per_page

    def for_text(self, text):
        return {
            'size_in_bytes': self.size_in_bytes(text),
            'char_count': self.char_count(text),
            'char_with_spaces_count': self.char_with_spaces_count(text),
            'word_count': self.word_count(text),
            'sentence_count': self.sentence_count(text),
            'paragraph_count': self.paragraph_count(text),
            'page_count': self.page_count(text)
        }
