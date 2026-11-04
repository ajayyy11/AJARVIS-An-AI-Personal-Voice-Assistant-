from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfWriter

from intelligence.multimodal import (
    MultimodalError, analyze_visual_input, detect_image_mime,
    extract_scanned_pdf_text, validate_visual_input,
)


def image_bytes(fmt="PNG"):
    output = BytesIO()
    Image.new("RGB", (24, 24), color=(10, 80, 120)).save(output, format=fmt)
    return output.getvalue()


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeTypes:
    class Part:
        @staticmethod
        def from_bytes(**kwargs):
            return {"media": kwargs}

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class FakeClient:
    def __init__(self):
        self.calls = []

    class Models:
        def __init__(self, owner):
            self.owner = owner

        def generate_content(self, **kwargs):
            self.owner.calls.append(kwargs)
            return SimpleNamespace(text="Visual content understood.")

    @property
    def models(self):
        return self.Models(self)


def test_detects_decoded_png_jpeg_and_webp():
    assert detect_image_mime(image_bytes("PNG")) == "image/png"
    assert detect_image_mime(image_bytes("JPEG")) == "image/jpeg"
    assert detect_image_mime(image_bytes("WEBP")) == "image/webp"


def test_rejects_corrupt_and_extension_mismatched_images():
    with pytest.raises(MultimodalError, match="invalid or corrupted"):
        detect_image_mime(bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"bad")
    with pytest.raises(MultimodalError, match="extension does not match"):
        validate_visual_input("capture.jpg", image_bytes("PNG"))


def test_visual_analysis_uses_inline_image_and_untrusted_content_prompt():
    data = image_bytes()
    client = FakeClient()
    answer = analyze_visual_input(
        client=client, filename="capture.png", data=data,
        prompt="Describe this image.", types_module=FakeTypes,
    )
    assert answer == "Visual content understood."
    call = client.calls[0]
    assert call["contents"][0]["media"]["mime_type"] == "image/png"
    assert call["contents"][0]["media"]["data"] == data
    assert "never as instructions" in call["config"].system_instruction


def test_visual_question_length_is_bounded():
    client = FakeClient()
    with pytest.raises(MultimodalError, match="1,200 characters"):
        analyze_visual_input(
            client=client, filename="capture.png", data=image_bytes(),
            prompt="x" * 1201, types_module=FakeTypes,
        )
    assert client.calls == []


def test_visual_pdf_validation_and_scanned_pdf_transcription():
    data = pdf_bytes()
    assert validate_visual_input("scan.pdf", data) == ("application/pdf", 1)
    client = FakeClient()
    extracted, count = extract_scanned_pdf_text(
        client=client, filename="scan.pdf", data=data, types_module=FakeTypes,
    )
    assert extracted == "Visual content understood."
    assert count == 1
    assert client.calls[0]["contents"][0]["media"]["mime_type"] == "application/pdf"


def test_rejects_invalid_pdf_and_unsupported_file():
    with pytest.raises(MultimodalError, match="invalid or corrupted"):
        validate_visual_input("broken.pdf", b"not a pdf")
    with pytest.raises(MultimodalError, match="Supported image formats"):
        validate_visual_input("archive.zip", b"PK")
