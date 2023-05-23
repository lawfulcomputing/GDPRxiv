class PriceTerminateTranslateSpecification():
    def __init__(self, price_terminate_usd):
        self.price_terminate_usd = price_terminate_usd
    def is_satisfied_by(self, price):
        return (self.price_terminate_usd > 0.0 and price >= self.price_terminate_usd)
