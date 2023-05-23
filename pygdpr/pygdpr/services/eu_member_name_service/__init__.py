import os
import json

class EUMemberNameService:
    def for_code(self, country_code):
        name = None
        path = os.path.abspath('pygdpr/assets/eu-members.json')
        f = open(path, 'r')
        eu_members_items = json.load(f)
        f.close()
        for cand_code, cand_name in eu_members_items.items():
            if country_code.lower() == cand_code.lower():
                name = cand_name
                break
        return name
