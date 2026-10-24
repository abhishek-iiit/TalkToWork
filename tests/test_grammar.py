import unittest

from handsfree.grammar import Intent, parse_utterance


class GrammarTest(unittest.TestCase):
    def test_single_commands(self):
        self.assertEqual(parse_utterance("type hello"), [Intent("type", "hello")])
        self.assertEqual(parse_utterance("Send it."), [Intent("send")])
        self.assertEqual(parse_utterance("open Slack"), [Intent("open_app", "Slack")])
        self.assertEqual(parse_utterance("open VS Code"), [Intent("open_app", "Visual Studio Code")])

    def test_wake_word_prefix(self):
        self.assertEqual(
            parse_utterance("Hi Abhishek, open youtube.com"),
            [Intent("wake"), Intent("open_site", "https://youtube.com")],
        )
        self.assertEqual(parse_utterance("Hi Abhishek new tab"), [Intent("wake"), Intent("tab", "new tab")])

    def test_wake_word_variants(self):
        for heard in ["Hi Abhishek, new tab.", "Hey, Abishek. New tab.", "Hello Abhishek new tab", "Abhishek, new tab"]:
            self.assertEqual(parse_utterance(heard), [Intent("wake"), Intent("tab", "new tab")], heard)
        self.assertEqual(parse_utterance("Hi everyone, new tab")[0].kind, "unknown")

    def test_custom_wake_word(self):
        self.assertEqual(parse_utterance("Infina, new tab", "Infina")[0], Intent("wake"))
        self.assertEqual(parse_utterance("Infina, new tab")[0].kind, "unknown")

    def test_open_site_in_browser(self):
        self.assertEqual(
            parse_utterance("Open Firefox and open YouTube URL in it."),
            [Intent("open_app", "Firefox"), Intent("open_site", "https://www.youtube.com", "@last")],
        )
        self.assertEqual(
            parse_utterance("open weather in new york in Safari"),
            [Intent("open_site", "https://www.google.com/search?q=weather+in+new+york", "Safari")],
        )

    def test_unknown_site_becomes_search(self):
        self.assertEqual(
            parse_utterance("open weather in pune")[0].arg,
            "https://www.google.com/search?q=weather+in+pune",
        )

    def test_compound_chain(self):
        self.assertEqual(
            parse_utterance("open Slack, type can we move the call and send it"),
            [Intent("open_app", "Slack"), Intent("type", "can we move the call"), Intent("send")],
        )
        self.assertEqual(
            parse_utterance("open notes then type buy milk"),
            [Intent("open_app", "Notes"), Intent("type", "buy milk")],
        )

    def test_whisper_style_sentences(self):
        self.assertEqual(
            parse_utterance("Open Cusser. Type can we move the call. Send it."),
            [Intent("open_app", "Cursor"), Intent("type", "can we move the call"), Intent("send")],
        )

    def test_misheard_app_names(self):
        self.assertEqual(parse_utterance("open nodes"), [Intent("open_app", "Notes")])
        self.assertEqual(parse_utterance("open the door")[0].kind, "open_site")

    def test_dictated_command_words_stay_in_text(self):
        self.assertEqual(
            parse_utterance("type please open the door and send it tomorrow"),
            [Intent("type", "please open the door and send it tomorrow")],
        )

    def test_unrecognised_speech(self):
        self.assertEqual(parse_utterance("so anyway I told him"), [Intent("unknown", "so anyway I told him")])


if __name__ == "__main__":
    unittest.main()
