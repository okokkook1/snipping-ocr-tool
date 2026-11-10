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

BACKGROUND = "#f1f5f9"
SURFACE = "#ffffff"
INK = "#1e293b"
MUTED = "#475569"
BORDER = "#cbd5e1"
ACCENT = "#1d4ed8"
SELECTED = "#dbeafe"
FONT = "Microsoft JhengHei UI"

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
        self.root.geometry("940x660")
        self.root.minsize(760, 510)
        self.root.option_add("*Font", (FONT, 10))
        self._setup_style()

        self.ocr_engine = None
        self.current_image = None
        self.preview_tk = None
        self.var_traditional = tk.BooleanVar(value=True)

        self._init_ui()
        self._init_ocr_engine()

        # 註冊快速鍵
        self.root.bind("<Control-n>", lambda e: self.start_snipping())
        self.root.bind("<F2>", lambda e: self.start_snipping())

    def _setup_style(self):
        self.root.configure(background=BACKGROUND)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=(FONT, 10))
        style.configure("Title.TLabel", background=SURFACE, font=(FONT, 19, "bold"))
        style.configure("Section.TLabel", font=(FONT, 12, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Status.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("TButton", background=SURFACE, foreground=INK, bordercolor=BORDER,
                        font=(FONT, 10), padding=(12, 8))
        style.map("TButton", background=[("disabled", BACKGROUND), ("pressed", SELECTED), ("active", "#eff6ff")],
                  foreground=[("disabled", "#64748b")])
        style.configure("Accent.TButton", background=ACCENT, foreground=SURFACE, bordercolor=ACCENT,
                        font=(FONT, 10, "bold"), padding=(16, 10))
        style.map("Accent.TButton",
                  background=[("disabled", BACKGROUND), ("pressed", "#1e3a8a"), ("active", "#1e40af")])
        style.configure("TCheckbutton", background=SURFACE, foreground=INK, font=(FONT, 10), padding=(6, 8))
        style.map("TCheckbutton", background=[("active", "#eff6ff")])

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
        header = ttk.Frame(self.root, style="Surface.TFrame", padding=(20, 14))
        header.pack(fill=tk.X)
        ttk.Label(header, text="螢幕剪取與文字辨識", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="拖曳框選畫面上的文字，再編輯、複製或儲存辨識結果。",
                  style="Status.TLabel").pack(anchor=tk.W, pady=(3, 0))
        toolbar = ttk.Frame(header, style="Surface.TFrame")
        toolbar.pack(fill=tk.X, pady=(12, 0))
        self.btn_snip = ttk.Button(toolbar, text="開始框選  (F2)", style="Accent.TButton",
                                   command=self.start_snipping)
        self.btn_snip.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(toolbar, text="自動轉為繁體中文", variable=self.var_traditional,
                        command=self._on_toggle_traditional).pack(side=tk.LEFT)

        status_bar = ttk.Frame(self.root, style="Surface.TFrame", padding=(20, 12))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_status = ttk.Label(status_bar, text="正在初始化 OCR 引擎…", style="Status.TLabel")
        self.lbl_status.pack(fill=tk.X)
        self.lbl_status.bind("<Configure>", lambda event: self.lbl_status.configure(wraplength=event.width))

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=9, background=BACKGROUND,
                               borderwidth=0, relief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=20, pady=14)
        left_frame = ttk.Frame(paned, width=240, padding=(0, 0, 8, 0))
        paned.add(left_frame, minsize=160, stretch="never")
        ttk.Label(left_frame, text="截圖預覽", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.preview_canvas = tk.Canvas(left_frame, width=1, height=1, background=SURFACE,
                                        highlightthickness=1, highlightbackground=BORDER)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", self._update_preview)
        left_frame.pack_propagate(False)

        right_frame = ttk.Frame(paned, padding=(8, 0, 0, 0))
        result_header = ttk.Frame(right_frame)
        result_header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(result_header, text="辨識結果", style="Section.TLabel").pack(side=tk.LEFT)
        self.lbl_count = ttk.Label(result_header, text="0 字", style="Muted.TLabel")
        self.lbl_count.pack(side=tk.LEFT, padx=10)

        result_actions = ttk.Frame(right_frame)
        result_actions.pack(fill=tk.X, pady=(0, 8))
        self.btn_copy = ttk.Button(result_actions, text="複製文字", width=0, command=self.copy_text)
        self.btn_save_txt = ttk.Button(result_actions, text="另存 TXT", width=0, command=self.save_as_txt)
        self.btn_save_odt = ttk.Button(result_actions, text="另存 ODT", width=0, command=self.save_as_odt)
        self.btn_clear = ttk.Button(result_actions, text="清空", width=0, command=self.clear_all)
        for index, button in enumerate((self.btn_copy, self.btn_save_txt, self.btn_save_odt, self.btn_clear)):
            result_actions.columnconfigure(index, weight=1, uniform="result")
            button.grid(row=0, column=index, sticky="ew", padx=(0, 6))
        result_actions.update_idletasks()
        paned.add(right_frame, minsize=result_actions.winfo_reqwidth() + 8, stretch="always")

        self.text_editor = scrolledtext.ScrolledText(
            right_frame, width=24, height=6, wrap=tk.WORD, font=(FONT, 12), undo=True,
            background=SURFACE, foreground=INK, insertbackground=INK,
            selectbackground=SELECTED, selectforeground=INK, padx=12, pady=10,
            relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True)
        self.text_editor.bind("<<Modified>>", self._on_text_modified)
        self._update_result_controls()

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
            self._update_result_controls()
            self.text_editor.edit_modified(False)

    def _update_result_controls(self):
        content = self.text_editor.get("1.0", "end-1c")
        count = len(content.strip())
        self.lbl_count.config(text=f"{count} 字")
        for button in (self.btn_copy, self.btn_save_txt, self.btn_save_odt):
            button.state(["!disabled" if count else "disabled"])
        can_clear = (content or self.current_image is not None) and not self.btn_snip.instate(["disabled"])
        self.btn_clear.state(["!disabled" if can_clear else "disabled"])

    def start_snipping(self):
        """隱藏主視窗並啟動全螢幕截圖模式"""
        if self.btn_snip.instate(["disabled"]):
            return
        self.btn_snip.config(state=tk.DISABLED)
        self._update_result_controls()
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
            self.btn_snip.config(state=tk.NORMAL)
            self._update_result_controls()
            self.set_status("已取消截圖")
            return

        self.current_image = cropped_image
        self._update_preview()

        # 啟動非同步 OCR 辨識
        self.set_status("⏳ 正在辨識文字中，請稍候...")
        threading.Thread(target=self._run_ocr_worker, args=(cropped_image,), daemon=True).start()

    def _update_preview(self, event=None):
        """依照預覽區的可用空間顯示截圖。"""
        canvas = self.preview_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete("all")
        if self.current_image is None:
            canvas.create_text(width / 2, height / 2, text="完成框選後會在此顯示截圖。",
                               fill=MUTED, font=(FONT, 10), width=max(1, width - 24), justify=tk.CENTER)
            return
        img_copy = self.current_image.copy()
        img_copy.thumbnail((max(1, width - 24), max(1, height - 24)), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(img_copy)
        canvas.create_image(width / 2, height / 2, image=self.preview_tk)

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
        self._update_result_controls()
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
        self.preview_tk = None
        self.current_image = None
        self._update_preview()
        self._update_result_controls()
        self.set_status("已清空內容")


def main():
    root = tk.Tk()
    app = SnippingOCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
