from enum import Enum

# Source: https://cloud.google.com/translate/pricing
class TranslateQuotaLimit(Enum):
    UNLIMITED=-1

# https://cloud.google.com/translate/quotas#content
class TranslateQuotaService():
    chars_per_day = 10**9
    chars_per_100_secs = 10**6
    chars_per_100_secs_per_user = 10**4

    def set_chars_per_day(self, number):
        self.chars_per_day = number

    def set_chars_per_100_secs(self, number):
        self.chars_per_100_secs = number

    def set_chars_per_100_secs_per_user(self, number):
        self.chars_per_100_secs_per_user = number

    def get_chars_per_day(self):
        return self.chars_per_day

    def get_chars_per_100_secs(self):
        return self.chars_per_100_secs

    def get_chars_per_100_secs_per_user(self):
        return self.chars_per_100_secs_per_user
