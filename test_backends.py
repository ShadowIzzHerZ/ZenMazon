import io, json, os, unittest
from unittest import mock
from zen import payments, tools


class Payments(unittest.TestCase):
    def env(self, **kw):
        return mock.patch.dict(os.environ, {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", **kw})

    def test_no_keys_means_simulated(self):
        with self.env():
            self.assertEqual(payments.mode(), "simulated")
            self.assertIsNone(payments.pay("Priya", 100, "rent"))

    def test_live_keys_are_refused_and_never_called(self):
        with self.env(RAZORPAY_KEY_ID="rzp_live_abc", RAZORPAY_KEY_SECRET="s"), mock.patch("zen.net.urlopen") as call:
            self.assertIn("error", payments.pay("Priya", 100, "rent"))
            call.assert_not_called()

    def test_test_keys_create_an_order_in_paise(self):
        with self.env(RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s"), mock.patch("zen.net.urlopen", return_value=io.BytesIO(b'{"id":"order_X1"}')) as call:
            self.assertEqual(payments.pay("Priya", 12.5, "rent"), dict(provider="razorpay-test", id="order_X1"))
            self.assertEqual(json.loads(call.call_args[0][0].data)["amount"], 1250)

    def test_worlds_without_an_owner_never_call_out(self):
        with self.env(RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s"), mock.patch("zen.net.urlopen") as call:
            out = tools.send_payment(tools.World(), "Priya", 100, "rent")
            call.assert_not_called()
            self.assertNotIn("Razorpay", out["summary"])


if __name__ == "__main__":
    unittest.main()
