import nltk

class PreprocessWordsService():
    def for_words(self, words):
        if len(words) == 0:
            return []
        stop_words = set(nltk.corpus.stopwords.words('english'))
        words = [w for w in words if w.isalpha()]
        words = [w.lower() for w in words]
        words = [w for w in words if w not in stop_words]
        return words
