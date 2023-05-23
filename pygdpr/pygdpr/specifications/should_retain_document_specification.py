import datetime
from pygdpr.policies.gdpr_policy import GDPRPolicy

class ShouldRetainDocumentSpecification():
    def is_satisfied_by(self, cand): #cand = date
        today = datetime.date.today()
        margin = today - GDPRPolicy().implementation_date() # timedelta
        return today - margin <= cand <= today + margin
