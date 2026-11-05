use std::{fs, io::Read};

use anyhow::Result;

#[test]
fn text_and_odt_roundtrip() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let text = "第一行\nA  <tag> & B\t你好";
    let txt = temp.path().join("結果.txt");
    let odt = temp.path().join("結果.odt");
    super::export_text(&txt, text, false)?;
    super::export_text(&odt, text, true)?;
    assert_eq!(fs::read_to_string(txt)?, text);
    let mut archive = zip::ZipArchive::new(fs::File::open(odt)?)?;
    let mut mimetype = String::new();
    {
        let mut entry = archive.by_index(0)?;
        assert_eq!(entry.name(), "mimetype");
        assert_eq!(entry.compression(), zip::CompressionMethod::Stored);
        entry.read_to_string(&mut mimetype)?;
    }
    assert_eq!(mimetype, "application/vnd.oasis.opendocument.text");
    let mut content = String::new();
    archive
        .by_name("content.xml")?
        .read_to_string(&mut content)?;
    assert!(content.contains("<text:p>第一行</text:p>"));
    assert!(
        content.contains("A<text:s/><text:s/>&lt;tag&gt;<text:s/>&amp;<text:s/>B<text:tab/>你好")
    );
    Ok(())
}

#[test]
fn simplified_to_traditional() {
    assert_eq!(super::traditional("简体中文测试"), "簡體中文測試");
}

#[test]
#[ignore = "requires the original OCR models and ONNX Runtime DLL"]
fn recognizes_chinese_and_english() -> Result<()> {
    let mut engine = super::ocr_engine(&super::models_dir()?)?;
    let image = image::load_from_memory(include_bytes!("../fixtures/ocr.png"))?.to_rgb8();
    let text = super::recognize(&mut engine, &image)?;
    assert!(text.contains("OCR 2026"), "{text}");
    assert!(super::traditional(&text).contains("繁體中文"), "{text}");
    Ok(())
}
