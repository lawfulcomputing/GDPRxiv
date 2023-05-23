import os
import json
from pygdpr.models.common.eu_member import EUMember

class ListEUMembersService():
    def get(self):
        eu_members = []
        path = os.path.abspath('pygdpr/assets/eu-members.json')
        f = open(path, 'r')
        eu_members_items = json.load(f)
        f.close()
        for country_code, country_name, in eu_members_items.items():
            eu_member = EUMember(country_code)
            eu_members.append(eu_member)
        return eu_members
