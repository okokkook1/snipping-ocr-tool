# 螢幕剪取與 OCR 文字辨識工具

Windows x64 桌面工具。拖曳框選畫面後，可在本機離線辨識中英文，並預覽截圖、編輯或複製辨識結果。

## Windows x64 下載

[下載 Rust 免安裝版](https://github.com/okokkook1/snipping-ocr-tool/releases/download/v2.0.0/snipping-ocr-rust-windows-x64.zip)。完整解壓後雙擊 `SnippingOCR.exe`，並保留同一資料夾內的執行期資源。

- **F2** 或 **Ctrl+N** 開始框選，**Esc** 取消。
- 預設將辨識文字轉成繁體中文，可在介面切換。
- 支援另存 UTF-8 TXT 與 ODT。

## 從 Rust 原始碼編譯

在 Windows x64 安裝 Rust MSVC 工具鏈與 Visual Studio C++ Build Tools，並在專案根目錄執行：

```powershell
cargo build --manifest-path rust/Cargo.toml --release --locked
```

在 `rust` 資料夾內，將下載檔內的 `models` 資料夾與 `onnxruntime*.dll` 複製到 `target\release\`，即可執行 `target\release\snipping-ocr-tool.exe`。

要執行含實際引擎的測試，請先將執行期資源放到上述位置，並在 `rust` 資料夾內執行：

```powershell
$env:SNIPPING_OCR_MODELS = (Resolve-Path .\target\release\models).Path
$env:ORT_DYLIB_PATH = (Resolve-Path .\target\release\onnxruntime.dll).Path
cargo test --release --locked -- --include-ignored
```

## Python 舊版

[Python 版使用說明](README-python.md) · [Python 版 Windows 下載](https://github.com/okokkook1/snipping-ocr-tool/releases/tag/v1.1.0)
