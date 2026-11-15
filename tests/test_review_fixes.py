"""БД2: асуудлын бүртгэлийн (docs/II-4-10_Issue_Log.pdf) засвар бүрийг нотлох тест.

Ажиллуулах:  python -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
from ta_core import (Config, Simulation, SIM_START, STUDENT_WAITS,  # noqa: E402
                     STUDENT_WAKES_TA, TA_DONE, TA_START)


def run_sim(cfg, seconds):
    sim = Simulation(cfg)
    sim.start()
    time.sleep(seconds)
    sim.stop()
    return sim, sim.drain_events()


class TestM1ZeroChairs(unittest.TestCase):
    """M-1: TA унтаж байхад ирсэн оюутан хүлээлгийн сандал алгасаж шууд үйлчлүүлнэ."""

    def test_zero_chairs_sleeping_ta_still_serves(self):
        sim, ev = run_sim(Config(0, 5, 0.05, 0.05, seed=21), 1.5)
        self.assertGreater(sim.served, 0, "сандалгүй үед TA хэзээ ч үйлчлээгүй")
        for e in ev:
            self.assertEqual(e.waiting, ())
            self.assertEqual(e.free_chairs, 0)

    def test_direct_entry_sequence(self):
        """Унтаж буй TA: SIM_START → STUDENT_WAKES_TA → TA_START (сандалд суухгүй)."""
        _, ev = run_sim(Config(3, 1, 0.05, 0.05, seed=12), 0.8)
        kinds = [e.kind for e in ev]
        self.assertEqual(kinds[:3], [SIM_START, STUDENT_WAKES_TA, TA_START])
        wake = ev[1]
        self.assertEqual(wake.current, wake.student)   # шууд TA-ийн өрөөнд орсон
        self.assertEqual(wake.waiting, ())
        self.assertEqual(ev[2].student, wake.student)

    def test_one_student_at_a_time_with_zero_chairs(self):
        _, ev = run_sim(Config(0, 10, 0.02, 0.04, seed=22), 1.5)
        helping = None
        for e in ev:
            if e.kind == TA_START:
                self.assertIsNone(helping)
                helping = e.student
            elif e.kind == TA_DONE:
                self.assertEqual(helping, e.student)
                helping = None

    def test_fifo_including_direct_entries(self):
        _, ev = run_sim(Config(4, 8, 0.03, 0.06, seed=23), 2.0)
        admitted = [e.student for e in ev if e.kind in (STUDENT_WAITS, STUDENT_WAKES_TA)]
        started = [e.student for e in ev if e.kind == TA_START]
        self.assertGreater(len(started), 3)
        self.assertEqual(started, admitted[:len(started)])


class TestM3SleepAccuracy(unittest.TestCase):
    """M-3: тохируулсан хугацаа OS-ийн timer-ийн нарийвчлалаас үл хамааран биелнэ."""

    def test_sleep_matches_requested_duration(self):
        sim = Simulation(Config())
        for want in (0.3, 1.0):
            t0 = time.monotonic()
            sim._sleep(want)
            got = time.monotonic() - t0
            self.assertGreaterEqual(got, want * 0.98)
            self.assertLessEqual(got, want * 1.10 + 0.03, f"хүссэн {want} с, бодит {got:.3f} с")

    def test_pause_time_is_not_counted(self):
        sim = Simulation(Config())
        import threading
        sim.pause()
        threading.Timer(0.4, sim.resume).start()
        t0 = time.monotonic()
        sim._sleep(0.3)
        got = time.monotonic() - t0
        self.assertGreaterEqual(got, 0.65)      # 0.4 pause + 0.3 sleep
        self.assertLessEqual(got, 0.85)


class TestM1ConsoleEncoding(unittest.TestCase):
    """m-1: stdout нь UTF-8 биш үед консол горим унахгүй."""

    def test_console_mode_with_non_utf8_stdout(self):
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        p = subprocess.run(
            [sys.executable, os.path.join(SRC, "ta_core.py"), "--chairs", "2", "--students", "3",
             "--interval", "0.2", "--service", "0.2", "--duration", "1"],
            capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace")[-400:])
        self.assertIn("Дүн", p.stdout.decode("utf-8"))


class TestM6InvalidReset(unittest.TestCase):
    """m-6: буруу тохиргоотой reset() ажиллаж буй симуляцийг зогсоохгүй."""

    def test_invalid_reset_keeps_simulation_running(self):
        sim = Simulation(Config(3, 3, 0.03, 0.03, seed=4))
        sim.start()
        time.sleep(0.2)
        with self.assertRaises(ValueError):
            sim.reset(Config(num_chairs=99))
        self.assertTrue(sim.running)
        self.assertEqual(sim.config.num_chairs, 3)
        sim.drain_events()
        time.sleep(0.3)
        self.assertGreater(len(sim.drain_events()), 0)
        sim.stop()
        self.assertEqual(sim.alive_threads(), 0)


def make_dashboard():
    import tkinter as tk
    sys.path.insert(0, SRC)
    import ui
    ui.messagebox.showerror = lambda *a, **k: None
    try:
        root = tk.Tk()
    except tk.TclError as exc:          # дэлгэцгүй орчин
        raise unittest.SkipTest(f"Tk байхгүй: {exc}")
    root.withdraw()
    return root, ui.Dashboard(root)


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def set_form(app, **values):
    for key, val in values.items():
        app.form[key].delete(0, "end")
        app.form[key].insert(0, val)


class TestUiFixes(unittest.TestCase):
    def setUp(self):
        self.root, self.app = make_dashboard()

    def tearDown(self):
        self.app.close()

    def test_m4_counter_keeps_up_under_load(self):
        """m-4: ачаалал ихтэй үед дэлгэцийн 'served' core-оос хэт хоцрохгүй."""
        set_form(self.app, chairs="1", students="30", interval="0.05", service="0.02")
        self.app.start()
        pump(self.root, 4.0)
        core = self.app.sim.served
        lag = core - self.app.display_served
        self.assertGreater(core, 20)
        self.assertLessEqual(lag, 10, f"core={core}, дэлгэц={self.app.display_served}")

    def test_m5_step_shows_exactly_one_event(self):
        """m-5: STEP бүр яг нэг event харуулна."""
        set_form(self.app, chairs="3", students="5", interval="0.2", service="0.2")
        self.app.start()
        pump(self.root, 1.0)
        self.app.pause()
        pump(self.root, 0.3)
        for _ in range(8):
            before = self.app.event_number
            self.app.step()
            deadline = time.monotonic() + 3
            while self.app.event_number == before and time.monotonic() < deadline:
                pump(self.root, 0.05)
            pump(self.root, 0.3)                      # нэмэлт event гарах эсэхийг хүлээнэ
            self.assertEqual(self.app.event_number, before + 1)

    def test_s1_seed_field(self):
        """S-1: UI-ийн seed талбар Config-д дамжина."""
        self.assertIn("seed", self.app.form)
        set_form(self.app, seed="42")
        self.assertEqual(self.app._read_config().seed, 42)
        set_form(self.app, seed="")
        self.assertIsNone(self.app._read_config().seed)


if __name__ == "__main__":
    unittest.main()
