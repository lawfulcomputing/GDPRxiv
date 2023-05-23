import os
from pygdpr.services.eu_member_name_service import EUMemberNameService

class DPAPathPolicy:
    def extend_gdpr_path(self, gdpr_path, country_code):
        country_code = country_code.upper()
        eu_member_name = EUMemberNameService()
        try:
            country_name = eu_member_name.for_code(country_code)
        except:
            raise ValueError(f"Could not find matching country name for country_code: {country_code}")
        country_name = country_name.replace(' ', '-').lower()
        dpa_path = os.path.abspath(f"{gdpr_path}/{country_name}")
        return dpa_path
