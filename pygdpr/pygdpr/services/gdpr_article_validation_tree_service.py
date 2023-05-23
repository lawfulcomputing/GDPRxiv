import os
import string
import json

class GDPRArticleValidationTreeService():
    def __init__(self):
        self.article_specs = [
            # (art., max. par., [(par_idx, max_let)])
            (1, 3, []),
            (2, 4, [(2, 'd')]),
            (3, 3, [(2, 'b')]),
            (4, 26, [(16, 'b'), (22, 'c'), (23, 'b')]),
            (5, 2, [(1, 'f')]),
            (6, 4, [(1, 'f'), (3, 'b'), (4, 'e')]),
            (7, 4, []),
            (8, 3, []),
            (9, 4, [(2, 'j')]),
            (10, None, []),
            (11, 2, []),
            (12, 8, [(5, 'b')]),
            (13, 4, [(1, 'f'), (2, 'f')]),
            (14, 5, [(1, 'f'), (2, 'g'), (3, 'c'), (5, 'd')]),
            (15, 4, [(1, 'h')]),
            (16, None, []),
            (17, 3, [(1, 'f'), (3, 'e')]),
            (18, 3, [(1, 'd')]),
            (19, None, []),
            (20, 4, [(1, 'b')]),
            (21, 6, []),
            (22, 4, [(2, 'c')]),
            (23, 2, [(1, 'j'), (2, 'h')]),
            (24, 3, []),
            (25, 3, []),
            (26, 3, []),
            (27, 5, [(2, 'b')]),
            (28, 10, [(3, 'h')]),
            (29, None, []),
            (30, 5, [(1, 'g'), (2, 'd')]),
            (31, None, []),
            (32, 4, [(1, 'd')]),
            (33, 5, [(3, 'd')]),
            (34, 4, [(3, 'c')]),
            (35, 11, [(3, 'c'), (7, 'd')]),
            (36, 5, [(3, 'f')]),
            (37, 7, [(1, 'c')]),
            (38, 6, []),
            (39, 2, [(1, 'e')]),
            (40, 11, [(2, 'k')]),
            (41, 6, [(2, 'd')]),
            (42, 8, []),
            (43, 9, [(1, 'b'), (2, 'e')]),
            (44, None, []),
            (45, 9, [(2, 'c')]),
            (46, 5, [(2, 'f'), (3, 'b')]),
            (47, 3, [(1, 'c'), (2, 'n')]),
            (48, None, []),
            (49, 6, [(1, 'g')]),
            (50, None, [(-1, 'd')]),
            (51, 4, []),
            (52, 6, []),
            (53, 4, []),
            (54, 2, [(1, 'f')]),
            (55, 3, []),
            (56, 6, []),
            (57, 4, [(1, 'v')]),
            (58, 6, [(1, 'f'), (2, 'j'), (3, 'j')]),
            (59, None, []),
            (60, 12, []),
            (61, 9, [(4, 'b')]),
            (62, 7, []),
            (63, None, []),
            (64, 8, [(1, 'f'), (5, 'b')]),
            (65, 6, [(1, 'c')]),
            (66, 4, []),
            (67, None, []),
            (68, 6, []),
            (69, 2, []),
            (70, 4, [(1, 'y')]),
            (71, 2, []),
            (72, 2, []),
            (73, 2, []),
            (74, 2, [(1, 'c')]),
            (75, 6, [(6, 'g')]),
            (76, 2, []),
            (77, 2, []),
            (78, 4, []),
            (79, 2, []),
            (80, 2, []),
            (81, 3, []),
            (82, 6, []),
            (83, 9, [(2, 'k'), (4, 'c'), (5, 'e')]),
            (84, 2, []),
            (85, 3, []),
            (86, None, []),
            (87, None, []),
            (88, 3, []),
            (89, 4, []),
            (90, 2, []),
            (91, 2, []),
            (92, 5, []),
            (93, 3, []),
            (94, 2, []),
            (95, None, []),
            (96, None, []),
            (97, 5, [(2, 'b')]),
            (98, None, []),
            (99, 2, [])
        ]
    def build(self, path='gdpr/assets/gdpr-article-validation-tree.json'):
        tree = {}
        alphabet = list(string.ascii_lowercase)
        for art, max_par, let_list in self.article_specs:
            if max_par is None and len(let_list) == 0:
                tree[str(art)] = True
            elif max_par is None and len(let_list) == 1:
                tree[str(art)] = {}
                let_par, max_let = let_list[0]
                assert let_par == -1
                let_range = alphabet[0:alphabet.index(max_let)+1]
                for let in let_range:
                    tree[str(art)][str(let)] = True
            else:
                tree[str(art)] = {}
                par_range = list(range(1, max_par+1))
                for par in par_range:
                    if len(let_list) == 0:
                        tree[str(art)][str(par)] = True
                    else:
                        for let_par, max_let in let_list:
                            if let_par == par:
                                tree[str(art)][str(par)] = {}
                                let_range = alphabet[0:alphabet.index(max_let)+1]
                                for let in let_range:
                                    tree[str(art)][str(par)][let] = True
                            elif str(par) not in tree[str(art)].keys():
                                tree[str(art)][str(par)] = True
        outfile = open(os.path.abspath(path), 'w')
        json.dump(tree, outfile, indent=4, sort_keys=True)
        outfile.close()
        return tree
