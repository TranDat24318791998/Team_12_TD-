import pytest
from growth_data.service import DataService
from growth_data.errors import Fault
from growth_data.seed import world
from growth_data.finance import safe_package


def test_calibration_view_is_scoped_past_only_and_memory_off_bypasses_it(tmp_path):
    calls=[]
    def provider(r,s,day):
        calls.append((r,s,day))
        return {"version":"memory-calibration-1","as_of_day":1,"points":5,"factor":.7,"q_low":.5,"q_high":.9}
    service=DataService(tmp_path,calibration_provider=provider)
    p=service.bootstrap()
    with service.store.connect(write=True) as c:
        a=service.create_run(c,p,{})["run_id"]
        b=service.create_run(c,p,{"memory_enabled":False})["run_id"]
        pkg=safe_package(175000,115000,world()["shops"]["D"]["private"]["rules"],300)
        with pytest.raises(Fault):service.forecast_values(c,a,"D",pkg,1)
        calls.clear()
        off=service.forecast_values(c,b,"D",pkg,2)
        assert off["factor_used"]==1 and calls==[]
        on=service.forecast_values(c,a,"D",pkg,2)
        assert on["factor_used"]==.7 and on["calibration_version"]=="memory-calibration-1"
        assert sum(on["daily_point_units"])==on["point"]
        assert on["low"]<=on["point"]<=on["high"]
