import unittest
import numpy as np
import pandas as pd
from detector import screen
from ranking import rank_signals

class RankingTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(44)
        self.e=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=90),'one':rng.normal(50,1,90),'two':rng.normal(50,1,90),'flat':[0.]*90})
        self.e.loc[[20,35,50,65,80],'one']=100
    def test_order_counts_and_unscored(self):
        table,results=rank_signals(self.e,['one','two','flat'])
        self.assertEqual(table.flagged_days.tolist(),sorted(table.flagged_days,reverse=True))
        self.assertEqual(table.set_index('signal').loc['flat','scored_days'],0)
        self.assertTrue(pd.isna(table.set_index('signal').loc['flat','flag_rate_pct']))
        for _,r in table.iterrows():
            self.assertEqual(r.flagged_days,int(results[r.signal].flag.sum()))
            self.assertEqual(r.upward_flags+r.downward_flags,r.flagged_days)
    def test_period_does_not_remove_baseline_history(self):
        t,out=rank_signals(self.e,['one'],period='Latest 30 days')
        expected=screen(self.e.set_index('date').one).tail(30).reset_index(drop=True)
        pd.testing.assert_frame_equal(out['one'],expected)
        self.assertEqual(len(out['one']),30)
    def test_settings_apply_to_every_signal(self):
        for mode in ['Prior rolling window','Fixed first 31 days']:
            for days in [7,30]:
                t,out=rank_signals(self.e,['one','two'],days=days,multiplier=2.5,mode=mode)
                for name in ['one','two']:
                    pd.testing.assert_frame_equal(out[name],screen(self.e.set_index('date')[name],days,2.5,mode))
if __name__=='__main__':unittest.main()
