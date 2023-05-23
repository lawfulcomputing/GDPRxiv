import os
import errno
import json

class SupportedDPASpecification:
    def is_satisfied_by(self, cand): # cand = country_code
        filename = 'dpa-info.json'
        path = os.path.abspath(f"pygdpr/assets/{filename}")
        if os.path.isfile(path) is False:
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), filename
            )
        f = open(path, 'r')
        dpa_info = json.load(f)
        f.close()
        country_codes = dpa_info.keys()
        return cand.upper() in country_codes
