class NotReachedDailyTranslateQuotaSpec():
    def __init__(self, quota_service):
        self.quota_service = quota_service
    def is_satisfied_by(self, quota):
        return (quota <= self.quota_service.get_chars_per_day() or\
                self.quota_service.get_chars_per_day() == -1) # -1 == Unlimited value
