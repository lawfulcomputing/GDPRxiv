class Pagination(object):
    def __init__(self):
        self.links = []
        self.cursor = 0

    def add_item(self, link):
        if link in self.links:
            return
        self.links.append(link)

    def reset_next(self):
        self.cursor = 0

    def has_next(self):
        return self.cursor <= len(self.links) - 1

    # Check if object has specific page link
    def has_link(self, link):
        if link in self.links:
            return True
        else:
            return False

    def get_next(self):
        if self.has_next() is False:
            raise ValueError('Pagination.get_next() cursor is out of bounds')

        link = self.links[self.cursor]
        self.cursor += 1
        return link

    def is_empty(self):
        return len(self.links) == 0
