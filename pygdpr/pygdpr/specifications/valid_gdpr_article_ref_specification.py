import os
import json

class ValidGDPRArticleRefSpecification():
    def is_satisfied_by(self, cand): # cand signature: (art, par, let)
        art, par, let = cand
        art = str(art) if art is not None else None
        par = str(par) if par is not None else None
        if art is None:
            return False
        if art.isdigit() == False:
            return False
        if par is not None and par.isdigit() == False:
            return False
        if let is not None and let.isalpha() == False:
            return False
        path = 'gdpr/assets/gdpr-article-validation-tree.json'
        f = open(os.path.abspath(path), 'r')
        validation_tree = json.load(f)
        f.close()
        if art not in validation_tree.keys():
            return False
        # assume: art exists in validation tree
        if par is not None:
            if let is None:
                return (par in validation_tree[art].keys())
            else:
                return (
                    par in validation_tree[art].keys() and\
                    let in validation_tree[art][par].keys()
                )
        # assume: par is None (null)
        if let is not None:
            return (let in validation_tree[art].keys())
        # assume: both par and let is None (null)
        return True
