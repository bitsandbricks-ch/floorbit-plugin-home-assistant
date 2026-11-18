"""The Home Assistant agent plugin: reading meters in the hall. Only localhost. (Floorbit's own
tests cover handing the readings to Electrics.)"""
import http.server
import json
import threading

import pytest
from conftest import load
from floorbit.plugins.agent import MemoryContext


class Fake(http.server.BaseHTTPRequestHandler):
    routes = {}  # noqa: RUF012  # set per test

    def do_GET(self):
        status, body = self.routes.get(self.path, (404, {}))
        if status == 401 and self.headers.get("Authorization") == "Bearer good-token":
            status, body = self.routes.get("ok:" + self.path, (404, {}))
        data = json.dumps(body).encode()
        self.send_response(status)
        if status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="x"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Fake.routes = {}
    yield f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_home_assistant_units_and_lines():
    m = load("agent")
    assert m.parse_sensors("db1-1 = sensor.a\nnope\ndb1-2=sensor.b") == [("db1-1", "sensor.a"), ("db1-2", "sensor.b")]
    unit = lambda u, v: {"state": v, "attributes": {"unit_of_measurement": u}}  # noqa: E731
    assert m.reading(unit("W", "120.5")) == {"watts": 120.5} and m.reading(unit("kW", "2.3")) == {"watts": 2300}
    assert m.reading(unit("A", "7")) == {"amps": 7} and m.reading(unit("W", "unavailable")) is None
    assert m.reading(unit("kWh", "5")) is None


def test_home_assistant_reads_and_stops_on_a_refused_token(fake):
    m = load("agent")
    states = [{"entity_id": "sensor.a", "state": "2.5", "attributes": {"unit_of_measurement": "kW"}},
              {"entity_id": "sensor.b", "state": "unknown", "attributes": {"unit_of_measurement": "W"}}]
    Fake.routes = {"/api/states": (401, {}), "ok:/api/states": (200, states)}
    sensors = "db1-1 = sensor.a\ndb1-2 = sensor.b\nx = sensor.c"
    settings = {"url": f"http://{fake}", "token": "good-token", "sensors": sensors}
    ctx = MemoryContext("home-assistant", settings, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.sensors, plugin.url, plugin.rev = m.parse_sensors(settings["sensors"]), settings["url"], "r1"
    readings, failed = plugin.tick()
    assert readings == [{"meter": "db1-1", "watts": 2500}] and len(failed) == 2 and "not found" in failed[1]
    ctx.settings["token"] = "wrong"
    plugin.tick()
    assert not ctx.may_login(settings["url"], "home-assistant", "r1")
    ctx.settings["token"] = "good-token"
    assert plugin.tick() == ([], ["token refused"])          # not tried again until cleared


def test_home_assistant_odd_answers_are_no_reading(fake):
    m = load("agent")
    for odd in ({"state": "nan", "attributes": {"unit_of_measurement": "W"}},
                {"state": "inf", "attributes": {"unit_of_measurement": "W"}},
                {"state": "5", "attributes": ["W"]}, {"state": "5"}, [], None):
        assert m.reading(odd) is None
    settings = {"url": f"http://{fake}", "token": "t", "sensors": "db1-1 = sensor.a"}
    ctx = MemoryContext("home-assistant", settings, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.sensors, plugin.url, plugin.rev = m.parse_sensors(settings["sensors"]), settings["url"], "r1"
    for body in ({"entity_id": "sensor.a"}, 5, [{"entity_id": ["sensor.a"]}, "x"]):
        Fake.routes = {"/api/states": (200, body)}
        assert plugin.tick()[0] == []


def test_a_round_that_breaks_does_not_stop_the_readings(monkeypatch):
    m = load("agent")
    ctx = MemoryContext("home-assistant", {}, {"sends": {}})
    agent = m.AgentPlugin(ctx)
    agent.interval = 0
    rounds = []

    def tick():
        rounds.append(1)
        if len(rounds) == 1:
            raise KeyError("surprise")
        ctx.stopping.set()

    monkeypatch.setattr(agent, "tick", tick)
    agent.loop()
    assert len(rounds) == 2
    assert any("a round failed" in e["error"] for e in ctx.health_.report()["errors"])
