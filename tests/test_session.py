import unittest

from handsfree.executor import ExecutorError, RecordingExecutor
from handsfree.session import Session


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ex = RecordingExecutor(frontmost="Notes")
        self.session = Session(self.ex, stay_awake=8, clock=self.clock)

    def statuses(self, utterance):
        return [r.status for r in self.session.handle(utterance)]

    def test_type_then_send(self):
        self.statuses("type hello")
        self.assertEqual(self.statuses("send it"), ["done"])
        self.assertEqual(self.ex.calls, [("type_text", "hello"), ("press_enter", None)])

    def test_send_presses_enter_once(self):
        self.statuses("type hello")
        self.statuses("send it")
        self.assertEqual(self.statuses("send it"), ["duplicate"])
        self.assertEqual(self.ex.calls.count(("press_enter", None)), 1)

    def test_unknown_speech_is_never_typed(self):
        self.assertEqual(self.statuses("so anyway I told him"), ["ignored"])
        self.assertEqual(self.ex.calls, [])

    def test_wake_word_required_for_sites_and_tabs(self):
        self.assertEqual(self.statuses("new tab"), ["ignored"])
        self.assertEqual(self.statuses("Hi Abhishek, new tab"), ["done", "done"])
        # Still awake: no prefix needed.
        self.clock.now += 5
        self.assertEqual(self.statuses("open youtube.com"), ["done"])
        # Stay-awake window restarts on each command, then lapses.
        self.clock.now += 9
        self.assertEqual(self.statuses("close this"), ["ignored"])

    def test_compound_chain_runs_in_order(self):
        self.assertEqual(self.statuses("open Slack, type hi team and send it"), ["done"] * 3)
        self.assertEqual(
            self.ex.calls,
            [("open_app", "Slack"), ("type_text", "hi team"), ("press_enter", None)],
        )

    def test_site_in_the_app_just_opened(self):
        self.assertEqual(self.statuses("Open Firefox and open YouTube URL in it."), ["done", "done"])
        self.assertEqual(
            self.ex.calls,
            [("open_app", "Firefox"), ("open_url", "https://www.youtube.com in Firefox")],
        )

    def test_site_alone_still_needs_wake_word(self):
        self.assertEqual(self.statuses("open youtube.com"), ["ignored"])
        self.assertEqual(self.ex.calls, [])

    def test_chain_with_unknown_step_does_nothing(self):
        self.assertEqual(self.statuses("blah blah, open Slack and type hi"), ["ignored"] * 3)
        self.assertEqual(self.ex.calls, [])

    def test_send_without_typing_is_held(self):
        self.assertEqual(self.statuses("send it"), ["needs_confirm"])
        self.assertNotIn(("press_enter", None), self.ex.calls)

    def test_send_after_switching_app_is_held_then_confirmed(self):
        self.statuses("type draft reply")
        self.statuses("open Slack")
        self.assertEqual(self.statuses("send it"), ["needs_confirm"])
        self.assertEqual(self.statuses("Hi Abhishek, confirm"), ["done", "done"])
        self.assertEqual(self.ex.calls[-1], ("press_enter", None))

    def test_stale_text_needs_confirm(self):
        self.statuses("type hello")
        self.clock.now += 61
        self.assertEqual(self.statuses("send it"), ["needs_confirm"])

    def test_confirm_expires(self):
        self.statuses("send it")
        self.clock.now += 11
        self.assertEqual(self.statuses("Hi Abhishek, confirm"), ["done", "ignored"])

    def test_chain_stops_at_held_send(self):
        self.assertEqual(self.statuses("send it, open Slack"), ["needs_confirm"])
        self.assertEqual(self.ex.calls, [])

    def test_scratch_that_removes_unsent_text(self):
        self.statuses("type hello")
        self.statuses("type world")
        self.assertEqual(self.statuses("Hi Abhishek, scratch that"), ["done", "done"])
        self.assertEqual(self.ex.calls[-1], ("delete_chars", len("hello world")))
        self.assertEqual(self.statuses("send it"), ["needs_confirm"])

    def test_scratch_that_cannot_unsend(self):
        self.statuses("type hello and send it")
        self.assertEqual(self.statuses("Hi Abhishek, scratch that"), ["done", "ignored"])

    def test_failed_open_stops_the_chain(self):
        def missing(app):
            raise ExecutorError(f"Unable to find application named '{app}'")

        self.ex.open_app = missing
        self.assertEqual(self.statuses("open Slack, type hi team and send it"), ["failed"])
        self.assertEqual(self.ex.calls, [])


if __name__ == "__main__":
    unittest.main()
