"""Run: python -m unittest discover -s . -p 'test_*.py'"""
import unittest
import pandas as pd
from engineering import evaluate

class EngineeringTests(unittest.TestCase):
    def test_extreme_flat_temperature_flags_immediately_and_preserves_raw(self):
        e=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=3),'1_rohigh_pressure_pump_qz_temp_o':[212.,212.,None]})
        original=e.copy(deep=True)
        events,_=evaluate(e,pd.DataFrame(),'Plant A')
        self.assertEqual(len(events),2)
        pd.testing.assert_frame_equal(e,original)
    def test_sec_no_zero_division_or_future_leakage(self):
        dates=pd.date_range('2026-01-01',periods=20)
        e=pd.DataFrame({'date':dates,'example':[1.]*20})
        p=pd.DataFrame({'date':dates,'effluent_volume_m3':[100.]*19+[0.], 'influent_volume_m3':[150.]*20,'daily_electricity_kwh':[100.]*14+[150.]*6})
        early,_=evaluate(e.iloc[:16],p.iloc[:16],'Plant A')
        full,_=evaluate(e,p,'Plant A')
        pd.testing.assert_frame_equal(early.reset_index(drop=True),full.loc[full.date<=dates[15]].reset_index(drop=True))
        self.assertTrue(full.title.eq('Electricity recorded with zero product').any())
        self.assertFalse(full.loc[full.signal.eq('calculated_sec_kwh_m3'),'value'].isna().any())
    def test_missing_day_breaks_streak(self):
        dates=pd.date_range('2026-01-01',periods=20)
        e=pd.DataFrame({'date':dates,'example':[1.]*20})
        p=pd.DataFrame({'date':dates,'effluent_volume_m3':[100.]*20,'influent_volume_m3':[150.]*20,'daily_electricity_kwh':[100.]*14+[150.]*6})
        p=p.drop(index=16)
        events,_=evaluate(e,p,'Plant A')
        after=events.loc[(events.date==dates[17])&events.signal.eq('calculated_sec_kwh_m3')]
        self.assertEqual(after.consecutive_days.iloc[0],1)
if __name__=='__main__': unittest.main()
