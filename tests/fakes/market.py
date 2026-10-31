"""Fixture contract for the market teammate; not a measured forecast."""

from app.domain.models.metrics import Forecast, ForecastSnapshot


class FakeMarket:
    source = 'fixture'

    def forecast_package(self, shop, pkg, day, seed, calibration):
        return Forecast(low=8, point=12, high=16, factor_used=calibration.factor, stock_warning=False)

    def build_forecast_snapshots(self, shop, pkg, start_day, seed, calibration):
        return [ForecastSnapshot(prediction_id=f'{shop.shop_id}:{start_day + i}', shop_id=shop.shop_id,
                 target_day=start_day + i, raw_point=4.0, issued_point=4, factor_used=calibration.factor,
                 package=pkg) for i in range(pkg.duration_days)]

    def simulate_day(self, session, day):
        from app.domain.models.metrics import DayMetrics
        state=session.states[session.settings.demo_shop]
        self.calls=getattr(self,'calls',0)+1
        orders=3
        state.public.stock-=orders
        return {state.public.shop_id:DayMetrics(shop_id=state.public.shop_id,day=day,impressions=1000,
            clicks=40,orders=orders,revenue=orders*state.public.price,ads_spend=18000,roas=4.0,
            fees=10000,profit_after_fees=10000)}
