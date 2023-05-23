class TranslateFilePolicy():
    allowed_formats = ['txt']
    def is_allowed(self, filename):
        split = filename.split('.')
        format_ = split[1]
        return (format_ in self.allowed_formats)
