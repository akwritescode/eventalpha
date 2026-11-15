import fakeredis

from eventalpha import watchdog


def test_reports_paused_dags_except_ignored():
    dags = [
        {"dag_id": "rss_news_hourly", "is_paused": "True"},
        {"dag_id": "maintenance", "is_paused": True},
        {"dag_id": "classify_articles", "is_paused": "False"},
        {"dag_id": "old_experiment", "is_paused": True},
    ]
    assert watchdog.paused_dags(dags, ignore=["old_experiment"]) == ["maintenance", "rss_news_hourly"]


def test_alert_lists_paused_and_broken_and_is_silent_when_healthy():
    assert watchdog.format_alert([], []) is None
    text = watchdog.format_alert(["rss_news_hourly"], ["/opt/airflow/dags/x.py"])
    assert "rss_news_hourly" in text and "x.py" in text


def test_each_problem_is_reported_once_until_it_clears():
    r = fakeredis.FakeRedis(decode_responses=True)
    assert watchdog.due(r, "paused", ["maintenance"]) == ["maintenance"]
    assert watchdog.due(r, "paused", ["maintenance"]) == []  # still paused: no repeat yet
    watchdog.clear(r, "paused", ["maintenance"])  # unpaused
    assert watchdog.due(r, "paused", ["maintenance"]) == ["maintenance"]  # paused again: alert now
