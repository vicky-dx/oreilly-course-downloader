import os
import json
import pytest
from oreilly_downloader.core.gmail_trick import get_dot_variation, GmailTrickState

def test_get_dot_variation():
    # Normal case: length 4 -> 3 spots -> 8 variations
    email = "abcd@gmail.com"
    # index 0: no dots -> abcd@gmail.com
    assert get_dot_variation(email, 0) == "abcd@gmail.com"
    # index 1: dot at spot 0 -> a.bcd@gmail.com
    assert get_dot_variation(email, 1) == "a.bcd@gmail.com"
    # index 2: dot at spot 1 -> ab.cd@gmail.com
    assert get_dot_variation(email, 2) == "ab.cd@gmail.com"
    # index 3: dot at spot 0 & 1 -> a.b.cd@gmail.com
    assert get_dot_variation(email, 3) == "a.b.cd@gmail.com"
    # index 7: all spots -> a.b.c.d@gmail.com
    assert get_dot_variation(email, 7) == "a.b.c.d@gmail.com"
    # index 8: wraps around to 0 -> abcd@gmail.com
    assert get_dot_variation(email, 8) == "abcd@gmail.com"

def test_get_dot_variation_normalization():
    # Dot normalization
    email = "a.b.c.d@gmail.com"
    assert get_dot_variation(email, 0) == "abcd@gmail.com"
    assert get_dot_variation(email, 7) == "a.b.c.d@gmail.com"

def test_get_dot_variation_non_gmail():
    # Non-gmail domain shouldn't strip dots from base if config is different,
    # but the trick itself should still partition spaces
    email = "ab.cd@custom.com"
    # Should keep original base email structure and apply dot variation on it
    # ab.cd has length 5, so 4 spots
    assert get_dot_variation(email, 0) == "ab.cd@custom.com"

def test_gmail_trick_state(tmp_path):
    output_dir = str(tmp_path)
    state = GmailTrickState(output_dir)
    
    # Assert initial defaults
    assert state.get_base_email() is None
    assert state.get_next_index() == 0
    
    # Set and persist base email
    state.set_base_email("test@gmail.com")
    assert state.get_base_email() == "test@gmail.com"
    
    # Increment index
    state.increment_index()
    assert state.get_next_index() == 1
    
    # Add history
    state.add_history("t.est@gmail.com", 0, "success")
    
    # Load state in new instance
    new_state = GmailTrickState(output_dir)
    assert new_state.get_base_email() == "test@gmail.com"
    assert new_state.get_next_index() == 1
    assert len(new_state.state["history"]) == 1
    assert new_state.state["history"][0]["email"] == "t.est@gmail.com"

def test_get_unused_random_index(tmp_path):
    output_dir = str(tmp_path)
    state = GmailTrickState(output_dir)
    state.set_base_email("abc@gmail.com") # 3 characters -> 2 spaces -> max 4 variations (index 0, 1, 2, 3)
    
    # Verify index 0 is excluded, so first choice must be in {1, 2, 3}
    idx = state.get_unused_random_index()
    assert idx in {1, 2, 3}
    
    # Mark index 1 as used
    state.add_history("a.bc@gmail.com", 1, "success")
    
    # Now available indices are in {2, 3}
    idx = state.get_unused_random_index()
    assert idx in {2, 3}
    
    # Mark indices 2 and 3 as used
    state.add_history("ab.c@gmail.com", 2, "success")
    state.add_history("a.b.c@gmail.com", 3, "success")
    
    # All indices are now used. It should recycle (excluding 0, i.e., in {1, 2, 3})
    idx = state.get_unused_random_index()
    assert idx in {1, 2, 3}

