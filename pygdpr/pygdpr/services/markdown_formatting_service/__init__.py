class MarkdownFormattingService:
    def format_markdown(self, path, values, prefix='{{', suffix='}}'):
        f = open(path, 'r')
        formatted_str = f.read()
        f.close()
        for key, value in values:
            if value is None:
                continue
            old = prefix + key + suffix
            new = str(value)
            formatted_str = formatted_str.replace(old, new)
        return formatted_str
