from pygdpr.services.metadata_service import MetadataService
import nltk
from collections import Counter
import heapq

class SummaryMetadataService(MetadataService):
    def for_text(self, text, num_sents=2):
        if len(text) == 0:
            return None
        sentence_list = nltk.sent_tokenize(text)
        stopwords = set(nltk.corpus.stopwords.words('english'))
        words = nltk.word_tokenize(text)
        # words = [w for w in words if w.isalpha()]
        words = [w for w in words if w not in stopwords]
        word_frequencies = dict(Counter(words))
        maximum_frequncy = max(word_frequencies.values())
        for word in word_frequencies.keys():
            word_frequencies[word] = (word_frequencies[word]/maximum_frequncy)
        sentence_scores = {}
        for sent in sentence_list:
            for word in nltk.word_tokenize(sent.lower()):
                if word in word_frequencies.keys():
                    if sent not in sentence_scores.keys():
                        sentence_scores[sent] = word_frequencies[word]
                    else:
                        sentence_scores[sent] += word_frequencies[word]
        summary_sentences = heapq.nlargest(num_sents, sentence_scores, key=sentence_scores.get)
        summary = ' '.join(summary_sentences)
        language_code = 'en'
        return {
            language_code: summary
        }
