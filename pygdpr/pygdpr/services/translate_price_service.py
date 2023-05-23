from enum import Enum

# Source: https://cloud.google.com/translate/pricing
class TranslateModelPrice(Enum):
    PBMT=20.0
    NMT=20.0
    AutoML=80.0

class TranslatePriceService():
    def price_for_text(self, text, model=TranslateModelPrice.PBMT):
        return model.value * (len(text) / 10.0**6)
