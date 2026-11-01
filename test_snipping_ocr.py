#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

# Add project path to sys.path
sys.path.insert(0, os.path.dirname(__file__))

from snipping_ocr import export_to_odt, export_to_txt, to_traditional_chinese, HAS_RAPID_OCR


class TestSnippingOCR(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_tmp")
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        for f in os.listdir(self.test_dir):
            try:
                os.remove(os.path.join(self.test_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.test_dir)
        except Exception:
            pass

    def test_export_to_txt(self):
        sample_text = "第 1 行：測試繁體中文與 English\n第 2 行：特殊符號 <>&\"' 測試\n12345"
        txt_path = os.path.join(self.test_dir, "output.txt")
        export_to_txt(txt_path, sample_text)
        self.assertTrue(os.path.exists(txt_path))

        with open(txt_path, "r", encoding="utf-8") as f:
            read_back = f.read()
        self.assertEqual(read_back, sample_text)

    def test_export_to_odt(self):
        sample_text = "第一行：你好世界\n特殊字元 <test> & \"quotes\"\nEnd line"
        odt_path = os.path.join(self.test_dir, "output.odt")
        export_to_odt(odt_path, sample_text)
        self.assertTrue(os.path.exists(odt_path))

        # Check ODT structure
        with zipfile.ZipFile(odt_path, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("mimetype", namelist)
            self.assertIn("META-INF/manifest.xml", namelist)
            self.assertIn("content.xml", namelist)

            # Check mimetype is uncompressed
            info = zf.getinfo("mimetype")
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            mimetype_content = zf.read("mimetype").decode("utf-8")
            self.assertEqual(mimetype_content, "application/vnd.oasis.opendocument.text")

            # Parse content.xml to ensure valid XML
            content_bytes = zf.read("content.xml")
            root = ET.fromstring(content_bytes)
            # Find all paragraphs in text namespace
            ns = {"office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
                  "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
            paragraphs = root.findall(".//text:p", ns)
            self.assertEqual(len(paragraphs), 3)
            self.assertEqual(paragraphs[0].text, "第一行：你好世界")
            self.assertEqual(paragraphs[1].text, '特殊字元 <test> & "quotes"')
            self.assertEqual(paragraphs[2].text, "End line")

    def test_rapid_ocr_recognition(self):
        if not HAS_RAPID_OCR:
            self.skipTest("RapidOCR not installed")

        from rapidocr_onnxruntime import RapidOCR
        import numpy as np

        engine = RapidOCR()
        # Create an image with English and numbers
        img = Image.new("RGB", (320, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((15, 25), "SNIP OCR 2026 TEST", fill=(0, 0, 0))

        img_np = np.array(img)
        result, _ = engine(img_np)
        self.assertIsNotNone(result)
        recognized_texts = " ".join(r[1] for r in result)
        self.assertTrue(any(k in recognized_texts for k in ["SNIP", "OCR", "2026", "TEST"]))

    def test_traditional_chinese_conversion(self):
        # 測試簡體轉繁體
        simplified = "简体中文测试，开发软件与内存"
        expected = "簡體中文測試，開發軟體與內存" # 或開發軟件與內存
        converted = to_traditional_chinese(simplified)
        self.assertIn("簡體中文", converted)
        self.assertIn("測試", converted)



if __name__ == "__main__":
    unittest.main()
