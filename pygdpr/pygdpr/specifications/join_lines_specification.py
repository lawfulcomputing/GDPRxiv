from nltk.tokenize import sent_tokenize, word_tokenize
import string

class JoinLinesSpecification():
    """
    A specification class which acts as a predicate determining if two lines should be joined.

    Methods
    -------
    is_satisfied_by(cand, next_cand)
        Returns True if the two candidate lines should be joined. Otherwise, False.
    """
    def is_satisfied_by(self, cand, next_cand):
        """Returns True if the two candidate lines should be joined. Otherwise, False.

        Parameters
        ----------
        cand : str
            The first line.
        next_cand : str
            The next line.

        Returns
        -------
        bool
            True if the two candidate lines should be joined. Otherwise, False
        """
        next_cand_words = word_tokenize(next_cand)
        if len(next_cand_words) == 0:
            return False
        return cand.endswith(tuple(set(string.punctuation))) is False and (next_cand_words[0].isalpha() and next_cand_words[0].islower())
