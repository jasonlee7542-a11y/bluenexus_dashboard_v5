import unittest
import pandas as pd
from engineering import evaluate
from insights import group_incidents,compare_production

class InsightTests(unittest.TestCase):
    def test_incident_gap_breaks_group_and_counts_days(self):
        e=pd.DataFrame({'date':pd.to_datetime(['2026-01-01','2026-01-02','2026-01-04']), '1_rohigh_pressure_pump_qz_temp_o':[212.,212.,212.]})
        ev,_=evaluate(e,pd.DataFrame(),'Plant A');inc=group_incidents(ev)
        self.assertEqual(sorted(inc.flagged_days.tolist()),[1,2])
        self.assertEqual(inc.incident_id.nunique(),2)
    def test_matched_comparison_ignores_future_and_wrong_output(self):
        p=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=8),'effluent_volume_m3':[100.]*6+[1000.,100.], 'daily_electricity_kwh':[100.]*5+[150.,10000.,10000.]})
        short=compare_production(p.iloc[:6]);full=compare_production(p)
        pd.testing.assert_frame_equal(short,full.iloc[:6])
        self.assertEqual(short.iloc[-1].status,'Elevated at similar production')
        self.assertEqual(full.iloc[6].status,'Insufficient comparable history')
        self.assertEqual(full.iloc[-1].peer_count,6)
    def test_flat_reference_and_invalid_denominator(self):
        p=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=7),'effluent_volume_m3':[100.]*6+[0.], 'daily_electricity_kwh':[100.]*7})
        c=compare_production(p)
        self.assertEqual(c.iloc[5].status,'No elevated SEC at similar production')
        self.assertEqual(c.iloc[-1].status,'Invalid / unavailable SEC')
if __name__=='__main__':unittest.main()
