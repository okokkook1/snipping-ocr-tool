#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
螢幕剪取與 OCR 文字辨識工具 (Snipping OCR Tool)
- 支援螢幕滑鼠矩形框選擷取
- 自動進行繁體/簡體中文、英數 OCR 辨識
- 即時編輯、複製文字
- 支援匯出另存為 .txt 或 .odt (OpenDocument Text) 格式
"""

import sys
import os
import threading
import zipfile
import xml.sax.saxutils
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from PIL import Image, ImageTk, ImageGrab

# 嘗試設置 Windows DPI 感知，避免高解析度螢幕截圖縮放位移
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# 嘗試導入 RapidOCR 與 OpenCC (簡轉繁工具)
try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_RAPID_OCR = True
except ImportError:
    HAS_RAPID_OCR = False

try:
    import opencc
    OPENCC_CONVERTER = opencc.OpenCC("s2t")
    HAS_OPENCC = True
except Exception:
    OPENCC_CONVERTER = None
    HAS_OPENCC = False


def to_traditional_chinese(text: str) -> str:
    """將文字轉換為繁體中文"""
    if HAS_OPENCC and OPENCC_CONVERTER and text:
        try:
            return OPENCC_CONVERTER.convert(text)
        except Exception:
            return text
    return text



def export_to_odt(filepath: str, text: str):
    """
    將文字輸出為合乎標準的 OpenDocument Text (.odt) 檔案。
    無需安裝外部龐大函式庫，遵循 OASIS ODF 規範。
    """
    lines = text.splitlines()
    if not lines:
        lines = [""]

    paragraphs = "".join(f"<text:p>{xml.sax.saxutils.escape(line)}</text:p>" for line in lines)
    
    manifest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
 <manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.text"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""

    content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 office:version="1.2">
 <office:body>
  <office:text>
   {paragraphs}
  </office:text>
 </office:body>
</office:document-content>"""

    with zipfile.ZipFile(filepath, "w") as zf:
        # mimetype 必須無壓縮且放在 zip 第一個位置
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", manifest_xml.encode("utf-8"))
        zf.writestr("content.xml", content_xml.encode("utf-8"))


def export_to_txt(filepath: str, text: str):
    """將文字輸出為純文字 UTF-8 檔案"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)


class SnippingOverlay:
    """全螢幕框選遮罩視窗"""
    def __init__(self, parent, on_snip_completed):
        self.parent = parent
        self.on_snip_completed = on_snip_completed

        # 先擷取全螢幕圖片
        try:
            self.screenshot = ImageGrab.grab(all_screens=True)
        except Exception:
            self.screenshot = ImageGrab.grab()

        self.top = tk.Toplevel(parent)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-topmost", True)
        self.top.config(cursor="cross")

        self.canvas = tk.Canvas(self.top, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.tk_screenshot = ImageTk.PhotoImage(self.screenshot)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_screenshot)

        # 半透明暗化矩形覆蓋全螢幕
        self.dim_rect = self.canvas.create_rectangle(
            0, 0, self.screenshot.width, self.screenshot.height,
            fill="#000000", stipple="gray50", outline=""
        )

        # 提示文字
        self.hint_text = self.canvas.create_text(
            self.screenshot.width // 2, 40,
            text="拖曳滑鼠左鍵框選要辨識的文字區域 ｜ 按 ESC 取消",
            fill="white", font=("Microsoft JhengHei UI", 14, "bold")
        )

        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.top.bind("<Escape>", lambda e: self.cancel())

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        # 繪製選擇框（亮藍色框線）
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00B0FF", width=2
        )

    def on_move_press(self, event):
        cur_x, cur_y = event.x, event.y
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x, end_y = event.x, event.y
        self.top.destroy()

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # 避免誤點（寬高大於 8 像素才算有效截圖）
        if (x2 - x1) > 8 and (y2 - y1) > 8:
            cropped = self.screenshot.crop((x1, y1, x2, y2))
            self.on_snip_completed(cropped)
        else:
            self.on_snip_completed(None)

    def cancel(self):
        self.top.destroy()
        self.on_snip_completed(None)


class SnippingOCRApp:
    """主應用程式 GUI 介面"""
    def __init__(self, root):
        self.root = root
        self.root.title("剪取與 OCR 辨識工具 (繁體中文版)")
        self.root.geometry("900x640")
        self.root.minsize(720, 500)

        # 設定風格與繁體字型
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # 設定整體介面字型為微軟正黑體 (Microsoft JhengHei UI)
        default_font = ("Microsoft JhengHei UI", 10)
        self.root.option_add("*Font", default_font)

        self.ocr_engine = None
        self.current_image = None
        self.preview_tk = None
        self.var_traditional = tk.BooleanVar(value=True)

        self._init_ui()
        self._init_ocr_engine()

        # 註冊快速鍵
        self.root.bind("<Control-n>", lambda e: self.start_snipping())
        self.root.bind("<F2>", lambda e: self.start_snipping())

    def _init_ocr_engine(self):
        """背景非同步初始化 OCR 引擎，不卡頓啟動"""
        def load_worker():
            global HAS_RAPID_OCR
            if HAS_RAPID_OCR:
                try:
                    self.ocr_engine = RapidOCR()
                    self.root.after(0, lambda: self.set_status("就緒 (OCR 核心載入完成，支援繁體中文與英文辨識)"))
                    return
                except Exception as e:
                    print("RapidOCR 初始化錯誤:", e)
            self.root.after(0, lambda: self.set_status("警告: 未找到 RapidOCR 引擎，請先執行 pip install rapidocr-onnxruntime"))

        threading.Thread(target=load_worker, daemon=True).start()

    def _init_ui(self):
        # 頂部工具列
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_snip = ttk.Button(toolbar, text="✂️ 開始框選 (F2)", command=self.start_snipping)
        self.btn_snip.pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_save_txt = ttk.Button(toolbar, text="💾 另存為 .txt", command=self.save_as_txt)
        self.btn_save_txt.pack(side=tk.LEFT, padx=4)

        self.btn_save_odt = ttk.Button(toolbar, text="📄 另存為 .odt", command=self.save_as_odt)
        self.btn_save_odt.pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_copy = ttk.Button(toolbar, text="📋 複製文字", command=self.copy_text)
        self.btn_copy.pack(side=tk.LEFT, padx=4)

        self.btn_clear = ttk.Button(toolbar, text="🧹 清空內容", command=self.clear_all)
        self.btn_clear.pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # 繁體中文自動轉換切換勾選框
        self.chk_traditional = ttk.Checkbutton(
            toolbar, text="強制轉繁體中文", variable=self.var_traditional, command=self._on_toggle_traditional
        )
        self.chk_traditional.pack(side=tk.LEFT, padx=6)

        # 主工作區 (左右分割：左側預覽縮圖，右側文字編輯區)
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 左側縮圖預覽框架
        left_frame = ttk.LabelFrame(paned, text=" 截圖預覽 ", padding=6)
        paned.add(left_frame, weight=1)

        self.preview_label = ttk.Label(left_frame, text="點擊「開始框選」以擷取圖片", anchor="center")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        # 右側文字編輯框架
        right_frame = ttk.LabelFrame(paned, text=" 辨識結果 (繁體中文編輯區) ", padding=6)
        paned.add(right_frame, weight=2)

        self.text_editor = scrolledtext.ScrolledText(
            right_frame, wrap=tk.WORD, font=("Microsoft JhengHei UI", 11), undo=True
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True)

        # 底部狀態列
        status_bar = ttk.Frame(self.root, padding=(8, 4))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(status_bar, text="正在初始化 OCR 引擎...", anchor="w")
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_count = ttk.Label(status_bar, text="字數: 0", anchor="e")
        self.lbl_count.pack(side=tk.RIGHT)

        # 監聽文字變更以更新字數
        self.text_editor.bind("<<Modified>>", self._on_text_modified)

    def _on_toggle_traditional(self):
        """當使用者切換繁體中文勾選時，立即將目前編輯區的文字做相應轉換"""
        if self.var_traditional.get():
            content = self.text_editor.get("1.0", tk.END).strip()
            if content:
                converted = to_traditional_chinese(content)
                self.text_editor.delete("1.0", tk.END)
                self.text_editor.insert(tk.END, converted)
                self.set_status("已轉換目前文字為繁體中文")

    def set_status(self, msg: str):
        self.lbl_status.config(text=msg)

    def _on_text_modified(self, event=None):
        if self.text_editor.edit_modified():
            content = self.text_editor.get("1.0", tk.END).strip()
            self.lbl_count.config(text=f"字數: {len(content)}")
            self.text_editor.edit_modified(False)

    def start_snipping(self):
        """隱藏主視窗並啟動全螢幕截圖模式"""
        self.set_status("請在螢幕上按住滑鼠左鍵並拖曳框選區域...")
        self.root.withdraw()
        # 延遲 250ms 等待主視窗完全隱藏，確保截圖乾淨
        self.root.after(250, self._launch_overlay)

    def _launch_overlay(self):
        SnippingOverlay(self.root, self.on_snip_completed)

    def on_snip_completed(self, cropped_image):
        """截圖結束回呼函式"""
        self.root.deiconify()
        if cropped_image is None:
            self.set_status("已取消截圖")
            return

        self.current_image = cropped_image
        self._update_preview(cropped_image)

        # 啟動非同步 OCR 辨識
        self.set_status("⏳ 正在辨識文字中，請稍候...")
        self.btn_snip.config(state=tk.DISABLED)
        threading.Thread(target=self._run_ocr_worker, args=(cropped_image,), daemon=True).start()

    def _update_preview(self, image: Image.Image):
        """更新左側預覽縮圖"""
        max_w, max_h = 320, 450
        img_copy = image.copy()
        img_copy.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(img_copy)
        self.preview_label.config(image=self.preview_tk, text="")

    def _run_ocr_worker(self, image: Image.Image):
        """在背景執行緒中進行 OCR 辨識"""
        try:
            if not self.ocr_engine:
                if HAS_RAPID_OCR:
                    self.ocr_engine = RapidOCR()
                else:
                    self.root.after(0, lambda: self._on_ocr_finished("", "未安裝 RapidOCR 引擎"))
                    return

            import numpy as np
            img_np = np.array(image.convert("RGB"))
            result, _ = self.ocr_engine(img_np)

            recognized_lines = []
            if result:
                for item in result:
                    # item 結構: [box_points, text, confidence]
                    text_str = item[1].strip()
                    if text_str:
                        recognized_lines.append(text_str)

            final_text = "\n".join(recognized_lines)
            self.root.after(0, lambda: self._on_ocr_finished(final_text, None))
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: self._on_ocr_finished("", err_msg))

    def _on_ocr_finished(self, text: str, error: str = None):
        """OCR 完成後更新介面"""
        self.btn_snip.config(state=tk.NORMAL)
        if error:
            messagebox.showerror("OCR 辨識錯誤", f"辨識時發生錯誤:\n{error}")
            self.set_status("辨識失敗")
            return

        if not text:
            self.set_status("⚠️ 未在框選範圍內偵測到任何文字")
            messagebox.showinfo("辨識結果", "未在框選區域內偵測到清晰文字，請再試一次。")
            return

        # 若啟用繁體中文轉換
        if self.var_traditional.get():
            text = to_traditional_chinese(text)

        # 填入文字編輯區
        self.text_editor.delete("1.0", tk.END)
        self.text_editor.insert(tk.END, text)
        line_count = len(text.splitlines())
        self.set_status(f"✅ 辨識完成！共識別出 {line_count} 行文字（{len(text)} 字元）")

    def save_as_txt(self):
        """另存為 .txt 純文字檔"""
        text = self.text_editor.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "目前沒有文字內容可儲存！")
            return

        filepath = filedialog.asksaveasfilename(
            title="另存為純文字檔",
            defaultextension=".txt",
            filetypes=[("純文字檔 (*.txt)", "*.txt"), ("所有檔案 (*.*)", "*.*")]
        )
        if not filepath:
            return

        try:
            export_to_txt(filepath, text)
            self.set_status(f"✅ 已成功儲存為純文字檔: {os.path.basename(filepath)}")
            messagebox.showinfo("儲存成功", f"檔案已成功儲存至:\n{filepath}")
        except Exception as e:
            messagebox.showerror("儲存失敗", f"寫入檔案時發生錯誤:\n{e}")

    def save_as_odt(self):
        """另存為 .odt (OpenDocument Text) 格式"""
        text = self.text_editor.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "目前沒有文字內容可儲存！")
            return

        filepath = filedialog.asksaveasfilename(
            title="另存為 OpenDocument 文件",
            defaultextension=".odt",
            filetypes=[("OpenDocument 文件 (*.odt)", "*.odt"), ("所有檔案 (*.*)", "*.*")]
        )
        if not filepath:
            return

        try:
            export_to_odt(filepath, text)
            self.set_status(f"✅ 已成功儲存為 ODT 檔案: {os.path.basename(filepath)}")
            messagebox.showinfo("儲存成功", f"檔案已成功儲存至:\n{filepath}\n可用 LibreOffice、Word 或 Google Docs 開啟。")
        except Exception as e:
            messagebox.showerror("儲存失敗", f"寫入 ODT 檔案時發生錯誤:\n{e}")

    def copy_text(self):
        """複製內容至剪貼簿"""
        text = self.text_editor.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "目前沒有文字可複製！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("📋 已將文字複製至剪貼簿")

    def clear_all(self):
        """清空預覽與文字"""
        self.text_editor.delete("1.0", tk.END)
        self.preview_label.config(image="", text="點擊「開始框選」以擷取圖片")
        self.preview_tk = None
        self.current_image = None
        self.set_status("已清空內容")


def main():
    root = tk.Tk()
    app = SnippingOCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
