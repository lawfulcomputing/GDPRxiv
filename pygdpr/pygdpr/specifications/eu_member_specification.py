import os
import errno
import json

class EUMemberSpecification():
    def is_satisfied_by(self, cand): # cand = country_code
        filename = 'eu-members.json'
        path = os.path.abspath(f"pygdpr/assets/{filename}")
        print("PATH: " + path)
        if os.path.isfile(path) is False:
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), filename
            )
        f = open(path, 'r')
        eu_members = json.load(f)
        f.close()
        country_codes = eu_members.keys()
        return cand.upper() in country_codes
