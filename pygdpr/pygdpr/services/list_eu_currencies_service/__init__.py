import os
import json

class ListEUCurrenciesService():
    def get(self):
        eu_currencies = {}
        path = os.path.abspath('pygdpr/assets/eu-currencies.json')
        f = open(path, 'r')
        eu_currencies_items = json.load(f)
        f.close()
        for country_code, currency in eu_currencies_items.items():
            currency_code = currency['code'].upper()
            if currency_code not in eu_currencies.keys():
                eu_currencies[currency_code] = currency
        return list(eu_currencies.values())
