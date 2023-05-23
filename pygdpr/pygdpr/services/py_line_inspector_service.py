class PyLineInspectorService():
    # subroutines
    def should_skip_line(self, i, lines):
        line = lines[i]
        return (i >= 0 and i <= len(lines) - 2) and line == '\n'

    def matching_start_line(self, line, type_, name):
        return line.lstrip(' ').startswith(type_ + ' ' + name)

    def matching_end_line(self, start_line, i, indentation):
        return indentation <= start_line[1] and i != start_line[0]-1

    def start_line_not_found(self, start_line):
        return start_line == (-1, -1)

    # main func
    def for_type_and_name(self, path, type_, name):
        if path.endswith('.py') is False:
            raise ValueError('Path is not a python file (.py):', path)

        start_line = (-1, -1) # (line, indentation)
        end_line = (-1, -1)

        with open(path, 'r') as f:
            lines = f.readlines()
            lines.append('') # Atom IDE approach is the same.
            for i in range(len(lines)):
                line = lines[i]
                indentation = 0

                for j in range(len(line)):
                    char = line[j]
                    if char == ' ':
                        indentation += 1
                    else:
                        break

                if self.should_skip_line(i, lines) is True:
                    continue

                # print('line %s - indentation:\t%d' % (i+1, indentation))
                if self.matching_start_line(line, type_, name) is True:
                    start_line = (i+1, indentation)

                # first, find start_line
                if self.start_line_not_found(start_line) is True:
                    continue

                # second, find end_line
                if self.matching_end_line(start_line, i, indentation) is True:
                    end_line = (i, indentation)
                    break

                #if line == lines[len(lines)-1] and (start_line != (-1, -1) and end_line == (-1, -1)):
                #    end_line = (i, indentation)
                #    break

        return (start_line[0], end_line[0])
