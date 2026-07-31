import unittest
from engine.risk import RiskManager

class TestRiskManager(unittest.TestCase):
    
    def test_drawdown_within_limits(self):
        rm = RiskManager(initial_balance=100000.0)
        # 1% drawdown (99,000)
        self.assertTrue(rm.check_drawdown(99000.0))
        
    def test_drawdown_exceeded(self):
        rm = RiskManager(initial_balance=100000.0)
        # 4% drawdown (96,000) - limit is 3.7%
        self.assertFalse(rm.check_drawdown(96000.0))

    def test_drawdown_exact_limit(self):
        rm = RiskManager(initial_balance=100000.0)
        # 3.7% drawdown (96,300)
        self.assertFalse(rm.check_drawdown(96300.0))
        
if __name__ == '__main__':
    unittest.main()
