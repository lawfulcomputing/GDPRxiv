class GDPRChapterSectionService():
    def __init__(self):
        self.comps_specs = [
            # (chapter, [(section:nullable, [min_art, max_art])])
            (1, [(None, [1,4])]),
            (2, [(None, [5,11])]),
            (3, [(1, [12,12]), (2, [13,15]), (3, [16,20]), (4, [21,22]), (5, [23,23])]),
            (4, [(1, [24,31]), (2, [32,34]), (3, [35,36]), (4, [37,39]), (5, [40,43])]),
            (5, [(None, [44, 50])]),
            (6, [(1, [51, 54]), (2, [55, 59])]),
            (7, [(1, [60, 62]), (2, [63, 67]), (3, [68, 76])]),
            (8, [(None, [77, 84])]),
            (9, [(None, [85, 91])]),
            (10, [(None, [92, 93])]),
            (11, [(None, [94, 99])])
        ]

    def for_article(self, article):
        chapter, section = None, None
        for cand_chapter, section_list in self.comps_specs:
            for cand_section, art_limit in section_list:
                min_art, max_art = art_limit[0], art_limit[1]
                if min_art <= article <= max_art:
                    chapter = cand_chapter
                    section = cand_section
                    break
        if chapter == None:
            raise AttributeError('Unable to infer chapter for value of article: ' + str(article))
        return (chapter, section)
