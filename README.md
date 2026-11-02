# 螢幕剪取與 OCR 文字辨識工具 (Snipping OCR Tool)

一個類似 Windows 剪取工具（Snipping Tool）的桌面 GUI 應用程式。使用者框選螢幕任意區域後，系統會自動擷取圖片、進行中英文文字辨識（OCR），並提供即時編輯、複製與另存為純文字（`.txt`）或 OpenDocument 文件（`.odt`）格式。

---

## ✨ 主要功能

1. **類似 Windows 剪取工具的框選介面**：
   - 點擊「開始框選」或快捷鍵 `F2` / `Ctrl+N`，主視窗自動縮小隱藏。
   - 全螢幕半透明遮罩，滑鼠左鍵拖曳拉出矩形選區，放開後自動截取。
   - 支援隨時按 `ESC` 取消截圖。
   - 支援 Windows 高解析度 DPI 縮放感知，框選精確無偏差。
2. **自動 OCR 文字辨識與全繁體中文支援**：
   - 全介面採用標準微軟正黑體（Microsoft JhengHei UI）繁體中文顯示。
   - 採用 RapidOCR (ONNX 離線引擎)，支援繁體中文、簡體中文、英文字母、數字與常見符號。
   - 內建繁體中文轉換機制（預設勾選「強制轉繁體中文」），確保即使來源圖像為簡體或辨識模型輸出簡體字，也能一鍵自動轉化為標準繁體字。
   - 多執行緒非同步處理，辨識時介面流暢不凍結。
3. **即時編輯與預覽**：
   - 左側提供截圖縮圖預覽，右側提供多行文字編輯器可即時校對與編輯。
   - 即時計算字數與狀態提示。
   - 提供「📋 複製文字」一鍵複製到系統剪貼簿。
4. **多格式匯出**：
   - 💾 **另存為 .txt**：標準 UTF-8 編碼純文字檔。
   - 📄 **另存為 .odt**：原生支援 OpenDocument Text 規範（相容 LibreOffice、Word、Google 文件）。

---

## 📥 下載離線版本 (免安裝 Python)

若您的電腦未安裝 Python 環境，可直接從 GitHub Releases 下載打包好的版本：

### 🌟 推薦：離線免安裝壓縮檔（極速秒開版）
👉 **[下載最新版 SnippingOCR-portable-windows-x64.zip](https://github.com/okokkook1/snipping-ocr-tool/releases/latest/download/SnippingOCR-portable-windows-x64.zip)**
- **特點**：預先解開所有模型與相依庫，解壓縮至任意資料夾後，雙擊 `SnippingOCR.exe` 即可**極速秒開**，沒有單一執行檔每次啟動的解壓延遲。
- 完整包含 RapidOCR 離線模型與 OpenCC 繁體中文轉換核心，100% 離線運作。

### 📦 單一獨立執行檔版
👉 **[下載 SnippingOCR.exe](https://github.com/okokkook1/snipping-ocr-tool/releases/download/v1.0.0/SnippingOCR.exe)**
- **特點**：單一檔案攜帶方便，但因每次啟動需在背景動態解壓 100MB 模組至暫存區，初次啟動時間較長（約需數秒）。

---

## 🚀 快速開始 (源碼執行)

### 1. 安裝相依套件
在命令提示字元 (cmd) 或 PowerShell 中執行：
```bash
pip install -r requirements.txt
```

### 2. 啟動程式
- **方式一（推薦）**：在 Windows 檔案總管中直接雙擊執行 `run.bat`。
- **方式二**：在終端機輸入：
  ```bash
  python snipping_ocr.py
  ```

---

## ⌨️ 快捷鍵一覽

| 快捷鍵 | 動作 |
|---|---|
| `F2` 或 `Ctrl + N` | 開始新截圖（框選螢幕） |
| `ESC` | 取消目前框選狀態 |
| `Ctrl + Z` | 在編輯器中復原變更 |
| `Ctrl + Y` | 在編輯器中重做變更 |
