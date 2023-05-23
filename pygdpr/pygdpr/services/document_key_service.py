import datetime
import random
import math

class DocumentKeyService():
    def __init__(self, kind, release_date, country_code):
        self.kind = kind
        self.release_date = release_date
        self.country_code = country_code

    def get_control_char(self, YYMMDD, ZZZZ):
        # omitted ambiguous letters: G, I, O, Q, Z
        pick_str = "0123456789ABCDEFHJKLMNPRSTUVWXY"
        idx = (int(YYMMDD) + int(ZZZZ)) / len(pick_str)
        idx = idx - int(idx)
        idx = idx * len(pick_str)
        idx = math.ceil(idx)
        return pick_str[idx]

    def push_key(self):
        K = self.kind[0:2].upper()
        YYMMDD = self.release_date.strftime("%y%m%d")
        ZZZZ = str(random.randint(0, 9999)).zfill(4)
        Q = self.get_control_char(YYMMDD, ZZZZ)
        C = self.country_code.upper()
        # valid separators in URL components.
        return f"{K}{YYMMDD}-{ZZZZ}{Q}+{C}"
