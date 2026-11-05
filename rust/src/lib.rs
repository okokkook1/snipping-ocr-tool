use std::{fs, io::Write, path::Path, sync::OnceLock};

use anyhow::{Context, Result};
use image::RgbImage;
use opencc_fmmseg::OpenCC;
use rapidocr_core::{RapidOcr, model::PPOCRV4_EN_MOBILE};
use zip::{ZipWriter, write::SimpleFileOptions};

#[cfg(test)]
mod tests;

pub fn traditional(text: &str) -> String {
    static OPENCC: OnceLock<OpenCC> = OnceLock::new();
    OPENCC.get_or_init(OpenCC::new).s2t(text, false)
}

pub fn ocr_engine(models: &Path) -> Result<RapidOcr> {
    // The original RapidOCR Chinese v4 model uses the same stage shapes as its v4 English preset.
    let mut config = PPOCRV4_EN_MOBILE.config(models);
    config.det.as_mut().unwrap().model_path = models.join("ch_PP-OCRv4_det_infer.onnx");
    config.cls.as_mut().unwrap().model_path = models.join("ch_ppocr_mobile_v2.0_cls_infer.onnx");
    let recognizer = config.rec.as_mut().unwrap();
    recognizer.model_path = models.join("ch_PP-OCRv4_rec_infer.onnx");
    recognizer.dict_path = models.join("ppocr_keys.txt");
    RapidOcr::new(config).with_context(|| format!("無法載入 OCR 模型：{}", models.display()))
}

pub fn recognize(engine: &mut RapidOcr, image: &RgbImage) -> Result<String> {
    Ok(engine
        .run_image(image)?
        .lines
        .iter()
        .map(|line| line.text.trim())
        .collect::<Vec<_>>()
        .join("\n"))
}

pub fn models_dir() -> Result<std::path::PathBuf> {
    if let Some(path) = std::env::var_os("SNIPPING_OCR_MODELS") {
        return Ok(path.into());
    }
    let executable = std::env::current_exe()?;
    Ok(executable
        .parent()
        .context("無法取得程式位置")?
        .join("models"))
}

pub fn export_text(path: &Path, text: &str, odt: bool) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let mut temp = tempfile::NamedTempFile::new_in(parent)?;
    if odt {
        write_odt(temp.as_file_mut(), text)?;
    } else {
        temp.write_all(text.as_bytes())?;
    }
    temp.persist(path)?;
    Ok(())
}

fn write_odt(file: &mut fs::File, text: &str) -> Result<()> {
    const MIME: &str = "application/vnd.oasis.opendocument.text";
    const MANIFEST: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"#;
    const CONTENT: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
<office:body><office:text>"#;

    let mut archive = ZipWriter::new(file);
    let stored = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Stored);
    archive.start_file("mimetype", stored)?;
    archive.write_all(MIME.as_bytes())?;
    archive.start_file("META-INF/manifest.xml", stored)?;
    archive.write_all(MANIFEST.as_bytes())?;
    archive.start_file("content.xml", stored)?;
    archive.write_all(CONTENT.as_bytes())?;
    for line in text.split('\n') {
        archive.write_all(b"<text:p>")?;
        let mut xml = String::new();
        for c in line.trim_end_matches('\r').chars() {
            match c {
                '&' => xml.push_str("&amp;"),
                '<' => xml.push_str("&lt;"),
                '>' => xml.push_str("&gt;"),
                ' ' => xml.push_str("<text:s/>"),
                '\t' => xml.push_str("<text:tab/>"),
                '\u{20}'..='\u{d7ff}' | '\u{e000}'..='\u{fffd}' | '\u{10000}'..='\u{10ffff}' => {
                    xml.push(c)
                }
                _ => {}
            }
        }
        archive.write_all(xml.as_bytes())?;
        archive.write_all(b"</text:p>")?;
    }
    archive.write_all(b"</office:text></office:body></office:document-content>")?;
    archive.finish()?;
    Ok(())
}
