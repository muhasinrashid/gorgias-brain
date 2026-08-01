from decimal import Decimal

from django.test import SimpleTestCase
from djstripe.models import Coupon

from apps.utils.billing import get_discounted_price, get_price_display_with_currency


def _coupon(**stripe_data):
    # amount_off / percent_off are read-only properties backed by stripe_data
    return Coupon(stripe_data=stripe_data)


class GetDiscountedPriceTest(SimpleTestCase):
    def test_amount_off(self):
        self.assertEqual(get_discounted_price(Decimal("20"), _coupon(amount_off=5)), Decimal("15"))

    def test_amount_off_never_goes_negative(self):
        self.assertEqual(get_discounted_price(Decimal("20"), _coupon(amount_off=30)), 0)

    def test_coupon_without_discount_returns_amount(self):
        self.assertEqual(get_discounted_price(Decimal("20"), _coupon()), Decimal("20"))

    def test_percent_off(self):
        # regression test: percent_off comes out of stripe_data as an int/float and used
        # to raise TypeError when mixed with Decimal amounts
        self.assertEqual(get_discounted_price(Decimal("20"), _coupon(percent_off=25)), Decimal("15"))

    def test_fractional_percent_off(self):
        self.assertEqual(get_discounted_price(Decimal("20"), _coupon(percent_off=12.5)), Decimal("17.50"))


class GetPriceDisplayWithCurrencyTest(SimpleTestCase):
    def test_currency_with_sigil(self):
        self.assertEqual(get_price_display_with_currency(10, "usd"), "$10.00")
        self.assertEqual(get_price_display_with_currency(10.5, "eur"), "€10.50")

    def test_currency_without_sigil_uses_code(self):
        self.assertEqual(get_price_display_with_currency(10, "sek"), "10.00 SEK")

    def test_rounds_to_two_decimal_places(self):
        self.assertEqual(get_price_display_with_currency(10.999, "usd"), "$11.00")
