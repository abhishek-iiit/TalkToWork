import unittest

from handsfree.formatting import format_dictation


class FormattingTest(unittest.TestCase):
    def check(self, spoken, expected):
        self.assertEqual(format_dictation(spoken), expected)

    def test_fillers_removed(self):
        self.check("um can we uh meet", "can we meet")

    def test_self_correction_replaces_matching_words(self):
        self.check("move the call to 3pm no wait 4pm", "move the call to 4pm")
        self.check("send it to John scratch that to Mary", "send it to Mary")

    def test_email(self):
        self.check("mail jane at acme dot com", "mail jane@acme.com")

    def test_email_with_written_domain(self):
        self.check("my email is jane at acme.com", "my email is jane@acme.com")

    def test_plain_at_and_dot_untouched(self):
        self.check("meet at noon and draw a dot on the map", "meet at noon and draw a dot on the map")

    def test_paths_and_files(self):
        self.check("open src slash main dot py", "open src/main.py")

    def test_mention(self):
        self.check("thanks at sign priya", "thanks @priya")

    def test_spoken_punctuation(self):
        self.check("hi team comma ready question mark new line yes period", "hi team, ready?\nyes.")


if __name__ == "__main__":
    unittest.main()
