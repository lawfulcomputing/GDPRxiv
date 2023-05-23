from ..specifications.join_lines_specification import JoinLinesSpecification

class JoinLinesPDFToTextService():
    """
    A service class which joins broken up lines of text (eg. a newline mistakenly introduced midsentence).

    Methods
    -------
    seek_next(j, lines)
        Returns the next line with a length greater than 0 (None if none found).

    for_text(text)
        Returns a modified copy of the text with no broken up lines.
    """
    def seek_next(self, j, lines):
        """Returns the next line with a length greater than 0 (None if none found).

        Parameters
        ----------
        j : int
            The iterator
        lines : [str]
            The list of lines.

        Returns
        -------
        str
            the next line with a length greater than 0 (None if none found)
        """
        next_line = None
        while next_line is None and j < len(lines):
            if len(lines[j]) > 0:
                next_line = lines[j]
                break
            j += 1
        return next_line

    def for_text(self, text):
        """Returns a modified copy of the text with no broken up lines.

        Parameters
        ----------
        text : str
            The text with broken up lines.

        Returns
        -------
        str
            a modified copy of the text parameter with no broken up lines
        """
        if len(text) == 0:
            return ""
        text_mod = ""
        lines = text.split("\n")
        i = 0
        for i in range(len(lines)):
            line = lines[i]
            j = i+1
            next_line = self.seek_next(j, lines)
            if next_line is None:
                break
            print('line:', line)
            print('next_line:', next_line)
            if JoinLinesSpecification().is_satisfied_by(line, next_line):
                text_mod += ' ' + next_line
            else:
                text_mod += '\n'.join(lines[i:j+1])
            i = j
        return text_mod
