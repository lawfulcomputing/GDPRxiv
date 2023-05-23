import datetime

class RetainDocumentPolicy():
    for_release_date(self):
        today = datetime.datetime.now()
        gdpr_implementation_date = datetime.datetime.strptime('25-05-2018', '%d-%m-%Y')
        return gdpr_implementation_date <= release_date <= today
