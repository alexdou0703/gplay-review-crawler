from crawler.rate_limiter import RequestLimiter


def test_limiter_adapts_to_throttles_and_recovers():
    limiter = RequestLimiter(min_interval=0)
    limiter.record_throttle()
    assert limiter.cooldown > 0
    limiter.record_success()
    assert limiter.cooldown < 1
