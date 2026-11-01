from voicetool.cleanup import clean

F = ["um", "uh"]


def test_removes_fillers():
    assert clean("Um, check the uh database.", F, {}) == "Check the database."


def test_filler_inside_word_untouched():
    assert clean("The umbrella is here.", F, {}) == "The umbrella is here."


def test_replacements_whole_word_case_insensitive():
    assert clean("restart PM 2 now", F, {"pm 2": "pm2"}) == "Restart pm2 now"


def test_empty_and_filler_only():
    assert clean("", F, {}) == "" and clean("Um.", F, {}) == ""


def test_does_not_add_or_change_punctuation():
    assert clean("git status", F, {}) == "Git status"
