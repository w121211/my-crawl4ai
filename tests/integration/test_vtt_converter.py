"""Tests for VTT to text converter."""

from app.youtube.vtt_converter import vtt_to_text


def test_vtt_to_text_basic():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.200 --> 00:00:03.360
All right, so here we are, in front of the
elephants

00:00:05.318 --> 00:00:07.974
the cool thing about these guys is that they
have really...

00:00:07.974 --> 00:00:12.616
really really long trunks

00:00:12.616 --> 00:00:14.367
and that's cool

00:00:14.421 --> 00:00:15.733
(baaaaaaaaaaahhh!!)

00:00:16.881 --> 00:00:18.881
and that's pretty much all there is to
say"""

    result = vtt_to_text(vtt)

    assert "All right, so here we are, in front of the elephants" in result
    assert "really really long trunks" in result
    assert "(baaaaaaaaaaahhh!!)" in result
    assert "WEBVTT" not in result
    assert "-->" not in result
    assert "00:00" not in result


def test_vtt_to_text_paragraph_breaks():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
First paragraph

00:00:05.000 --> 00:00:07.000
Second paragraph"""

    result = vtt_to_text(vtt)

    assert "\n\n" in result
    assert "First paragraph" in result
    assert "Second paragraph" in result


def test_vtt_to_text_multiline_captions():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
This is a long caption
that spans multiple lines"""

    result = vtt_to_text(vtt)

    assert "This is a long caption that spans multiple lines" in result


def test_vtt_to_text_empty_input():
    result = vtt_to_text("")
    assert result == ""


def test_vtt_to_text_no_captions():
    vtt = """WEBVTT
Kind: captions"""

    result = vtt_to_text(vtt)
    assert result == ""
