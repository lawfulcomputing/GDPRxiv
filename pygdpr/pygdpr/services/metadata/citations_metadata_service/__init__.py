import re
from pygdpr.services.metadata_service import *
from pygdpr.services.gdpr_chapter_section_service import *
import nltk
from nltk.stem.porter import *
from pygdpr.specifications.absolute_date_specification import *
from pygdpr.specifications.valid_gdpr_article_ref_specification import *
from dateparser.search import *

class CitationsMetadataService():
    def dot_notation_matches(self, words):
        refs = []
        # new regex to support cases: 14.a, 14.2
        regex = r"(\d\d*)\.((\d\d*)\.)?([a-z])"
        art_group_num, par_group_num, let_group_num = 1, 3, 4
        for w in words:
            matches = re.finditer(regex, w)
            for matchNum, match in enumerate(matches, start=1):
                art, par, let = None, None, None
                # print ("Match {matchNum} was found at {start}-{end}: {match}".format(matchNum = matchNum, start = match.start(), end = match.end(), match = match.group()))
                for groupNum in range(0, len(match.groups())):
                    groupNum = groupNum + 1
                    if match.group(groupNum) is None:
                        continue
                    if groupNum == art_group_num:
                        art = int(match.group(groupNum))
                    elif groupNum == par_group_num:
                        par = int(match.group(groupNum))
                    elif groupNum == let_group_num:
                        let = str(match.group(groupNum))
                    else:
                        continue
                    # print ("Group {groupNum} found at {start}-{end}: {group}".format(groupNum = groupNum, start = match.start(groupNum), end = match.end(groupNum), group = match.group(groupNum)))
                if art is None:
                    continue
                refs.append((art, par, let))
        return refs

    def for_text(self, text):
        ps = PorterStemmer()
        sents = nltk.sent_tokenize(text)
        art_key = ps.stem('article')
        par_key = ps.stem('paragraph')
        # letter key too, necessary?
        # let_key = ps.stem('letter')
        leg_key = '2016/679'
        for s in sents:
            ws = nltk.word_tokenize(s)
            ws = [w.lower() for w in ws]
            ws = [ps.stem(w) for w in ws]
            art_idx = -1
            leg_idx = -1
            try:
                art_idx = ws.index(art_key) # better to reuse: min(art_indices)?
            except:
                pass
            try:
                # leg_idx = ws.index(leg_key)
                leg_indices = [i for i, x in enumerate(ws) if x == leg_key]
                leg_idx = max(leg_indices)
            except:
                pass
            # if len(art_indices) == 0
            if art_idx == -1 or leg_idx == -1: # spec: gdprArticleRef.is_satisfied_by(s)
                continue
            #art_idx = art_indices[0]
            if art_idx > leg_idx: # support other case as well?
                continue
            ws_trim = ws[art_idx:leg_idx+1]
            matches = None
            try:
                matches = search_dates(" ".join(ws_trim), languages=['en'], settings={
                    'STRICT_PARSING': True,
                    'PREFER_DATES_FROM': 'past'
                })
            except:
                pass
            if matches is not None and len(matches) > 0:
                for m in matches:
                    if AbsoluteDateSpecification().is_satisfied_by(m):
                        snippet, date = m
                        snippet_ws = nltk.word_tokenize(snippet)
                        loc, len_ = -1, -1
                        for i in range(len(ws_trim)):
                            subset = ws_trim[i:i+len(snippet_ws)]
                            if subset == snippet_ws:
                                loc, len_ = i, i+len(snippet_ws)
                                break
                        if (loc != -1 and len_ != -1):
                            continue
                        del ws_trim[loc: len_]
            art_indices = [i for i, x in enumerate(ws_trim) if x == art_key]
            cand_arts = []
            for i in range(len(art_indices)):
                if i < len(art_indices)-1:
                    cand_arts.append(ws_trim[art_indices[i]:art_indices[i+1]])
                else:
                    cand_arts.append(ws_trim[art_indices[i]:])
            preds = []
            for cand in cand_arts:
                for i in range(1, len(cand)-1):
                    if cand[i].isdigit():
                        num = int(cand[i])
                        label = ''
                        if len(cand) >= 3 and (cand[i-1] == '(' and cand[i+1] == ')'):
                            label += 'par'
                        elif len(cand) >= 2 and (cand[i-1] == par_key):
                            label += 'par'
                        else:
                            label += 'art'
                        preds.append((num, label))
                    elif cand[i].isalpha() and len(cand[i]) == 1:
                        letter = str(cand[i])
                        label = 'let'
                        preds.append((letter, label))
                    else:
                        continue
            cand_refs = []
            for i in range(len(preds)):
                num, label = preds[i]
                if label == 'art':
                    cand_refs.append((num, None, None))
                elif label == 'par':
                    knear_art = -1
                    for j in range(len(preds[:i])):
                        if preds[j][1] == 'art':
                            knear_art = j
                    cand_art = preds[knear_art][0] if knear_art != -1 else None
                    cand_par = num
                    cand_let = None
                    cand_refs.append((cand_art, cand_par, cand_let))
                elif label == 'let':
                    knear_art, knear_par = -1, -1
                    for j in range(len(preds[:i])):
                        if preds[j][1] == 'art':
                            knear_art = j
                        elif preds[j][1] == 'par':
                            knear_par = j
                        else:
                            continue
                    cand_art = preds[knear_art][0] if knear_art != -1 else None
                    cand_par = preds[knear_par][0] if knear_par != -1 else None
                    cand_let = num
                    cand_refs.append((cand_art, cand_par, cand_let))
                else:
                    continue
            refs = []
            refs.extend(self.dot_notation_matches(ws_trim))
            i = 0
            while i < len(cand_refs):
                art, par, let = cand_refs[i]
                if i < len(cand_refs)-1:
                    if par is None and (cand_refs[i+1][0] == art and cand_refs[i+1][1] is not None):
                        refs.append(cand_refs[i+1])
                        i += 2
                    else:
                        refs.append(cand_refs[i])
                        i += 1
                else:
                    refs.append(cand_refs[i])
                    break
            final_refs = []
            j = 0
            while j < len(refs):
                art, par, let = refs[j]
                if j < len(refs)-1:
                    if let is None and ((refs[j+1][0] == art and refs[j+1][1] == par) and refs[j+1][2] is not None):
                        final_refs.append(refs[j+1])
                        j += 2
                    else:
                        final_refs.append(refs[j])
                        j += 1
                else:
                    final_refs.append(refs[j])
                    break
            valid_refs = []
            for ref in final_refs:
                if ValidGDPRArticleRefSpecification().is_satisfied_by(ref):
                    valid_refs.append(ref)
            article_refs = []
            for art, par, let in valid_refs:
                chapter, section = GDPRChapterSectionService().for_article(art)
                article_refs.append({
                    'chapter': chapter,
                    'section': section,
                    'article': art,
                    'paragraph': par,
                    'letter': let
                    # links['en'] = 'url' eur-lex.europa
                })
            return article_refs
