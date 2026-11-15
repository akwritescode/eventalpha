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


def test_failed_telegram_send_never_logs_the_bot_token(monkeypatch, caplog):
    from types import SimpleNamespace

    import httpx

    from eventalpha import alerts

    token = "123456:SECRET-TOKEN"
    monkeypatch.setattr(
        alerts.httpx,
        "post",
        lambda url, **kw: httpx.Response(
            400, json={"description": "Bad Request: chat not found"}, request=httpx.Request("POST", url)
        ),
    )
    s = SimpleNamespace(telegram_bot_token=token, telegram_ops_chat_id="-100", telegram_chat_id=None)
    assert alerts.send_telegram(s, "hi", ops=True) is False
    assert "chat not found" in caplog.text and token not in caplog.text


def test_a_fixed_import_error_is_forgotten_so_a_new_break_alerts_again():
    r = fakeredis.FakeRedis(decode_responses=True)
    assert watchdog.due(r, "broken", ["dags/a.py"]) == ["dags/a.py"]
    watchdog.forget_resolved(r, "broken", [])  # a.py imports again: off the error list
    assert watchdog.due(r, "broken", ["dags/a.py"]) == ["dags/a.py"]  # broken again: alert now
    watchdog.forget_resolved(r, "broken", ["dags/a.py"])  # still broken: keep the mark
    assert watchdog.due(r, "broken", ["dags/a.py"]) == []


def test_failure_alert_survives_a_missing_map_index():
    from types import SimpleNamespace

    from eventalpha.alerts import format_task_failure

    ti = SimpleNamespace(dag_id="d", task_id="t", map_index=None, try_number=1)
    assert "d" in format_task_failure({"task_instance": ti, "run_id": "r", "exception": None})
