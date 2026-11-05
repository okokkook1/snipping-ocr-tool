#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{path::PathBuf, sync::mpsc, thread, time::Duration};

use anyhow::Result;
use eframe::egui::{self, FontData, FontDefinitions, FontFamily, ViewportCommand};
use image::{DynamicImage, RgbImage};
use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use rfd::FileDialog;
use snipping_ocr_tool::{export_text, models_dir, ocr_engine, recognize, traditional};
use windows_sys::Win32::UI::HiDpi::{
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, SetProcessDpiAwarenessContext,
};

mod overlay;

enum Event {
    Engine(Result<()>),
    Capture(Result<Option<RgbImage>>),
    Recognized(Result<String>),
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    Idle,
    Selecting,
    Recognizing,
}

struct App {
    events: mpsc::Receiver<Event>,
    notify: mpsc::Sender<Event>,
    submit: mpsc::Sender<RgbImage>,
    state: State,
    text: String,
    force_traditional: bool,
    status: String,
    preview: Option<egui::TextureHandle>,
}

impl App {
    fn new(ctx: &egui::Context) -> Self {
        if let Ok(font) = std::fs::read(r"C:\Windows\Fonts\msjh.ttc") {
            let mut fonts = FontDefinitions::default();
            fonts
                .font_data
                .insert("jhenghei".into(), FontData::from_owned(font).into());
            for family in [FontFamily::Proportional, FontFamily::Monospace] {
                fonts
                    .families
                    .entry(family)
                    .or_default()
                    .push("jhenghei".into());
            }
            ctx.set_fonts(fonts);
        }

        let (notify, events) = mpsc::channel();
        let (submit, jobs) = mpsc::channel();
        let worker = notify.clone();
        let ctx = ctx.clone();
        thread::spawn(move || {
            let mut engine = match models_dir().and_then(|path| ocr_engine(&path)) {
                Ok(engine) => {
                    let _ = worker.send(Event::Engine(Ok(())));
                    engine
                }
                Err(error) => {
                    let _ = worker.send(Event::Engine(Err(error)));
                    ctx.request_repaint();
                    return;
                }
            };
            ctx.request_repaint();
            for image in jobs {
                let _ = worker.send(Event::Recognized(recognize(&mut engine, &image)));
                ctx.request_repaint();
            }
        });
        Self {
            events,
            notify,
            submit,
            state: State::Idle,
            text: String::new(),
            force_traditional: true,
            status: "正在初始化離線 OCR…".into(),
            preview: None,
        }
    }

    fn start_capture(&mut self, ctx: &egui::Context, frame: &eframe::Frame) {
        let Ok(handle) = frame.window_handle() else {
            self.status = "無法取得主視窗".into();
            return;
        };
        let RawWindowHandle::Win32(handle) = handle.as_raw() else {
            self.status = "此功能需要 Windows 桌面".into();
            return;
        };
        let hwnd = handle.hwnd.get();
        self.state = State::Selecting;
        self.status = "請拖曳框選文字區域…".into();
        ctx.send_viewport_cmd(ViewportCommand::Visible(false));
        let notify = self.notify.clone();
        let ctx = ctx.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(250));
            let _ = notify.send(Event::Capture(overlay::select_region()));
            // Wake the GUI even when Windows has suspended redraws for the hidden window.
            use windows_sys::Win32::UI::WindowsAndMessaging::{SW_SHOW, ShowWindowAsync};
            unsafe {
                ShowWindowAsync(hwnd as _, SW_SHOW);
            }
            ctx.request_repaint();
        });
    }

    fn update_events(&mut self, ctx: &egui::Context) {
        while let Ok(event) = self.events.try_recv() {
            match event {
                Event::Engine(result) => match result {
                    Ok(()) if self.status == "正在初始化離線 OCR…" => {
                        self.status = "就緒，支援中文與英文離線辨識".into();
                    }
                    Ok(()) => {}
                    Err(error) => {
                        if self.state == State::Recognizing {
                            self.state = State::Idle;
                        }
                        self.status = format!("{error:#}");
                    }
                },
                Event::Capture(result) => {
                    ctx.send_viewport_cmd(ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(ViewportCommand::Focus);
                    self.state = State::Idle;
                    match result {
                        Ok(Some(image)) => {
                            let preview = DynamicImage::ImageRgb8(image.clone())
                                .thumbnail(640, 900)
                                .to_rgb8();
                            let size = [preview.width() as usize, preview.height() as usize];
                            self.preview = Some(ctx.load_texture(
                                "screenshot",
                                egui::ColorImage::from_rgb(size, preview.as_raw()),
                                egui::TextureOptions::LINEAR,
                            ));
                            if self.submit.send(image).is_ok() {
                                self.state = State::Recognizing;
                                self.status = "正在辨識文字…".into();
                            } else {
                                self.status =
                                    "OCR 核心無法啟動，請確認 models 資料夾與執行檔放在一起".into();
                            }
                        }
                        Ok(None) => self.status = "已取消截圖".into(),
                        Err(error) => self.status = format!("{error:#}"),
                    }
                }
                Event::Recognized(result) => {
                    self.state = State::Idle;
                    match result {
                        Ok(text) if text.is_empty() => {
                            self.status = "框選範圍內未偵測到文字".into()
                        }
                        Ok(text) => {
                            self.text = if self.force_traditional {
                                traditional(&text)
                            } else {
                                text
                            };
                            self.status =
                                format!("辨識完成，共 {} 行文字", self.text.lines().count());
                        }
                        Err(error) => self.status = format!("辨識失敗：{error:#}"),
                    }
                }
            }
        }
    }

    fn save(&mut self, extension: &str) {
        let dialog = FileDialog::new()
            .set_title("另存辨識結果")
            .set_file_name(format!("ocr.{extension}"))
            .add_filter(extension.to_uppercase(), &[extension]);
        if let Some(path) = dialog.save_file() {
            let path: PathBuf = if path.extension().is_none() {
                path.with_extension(extension)
            } else {
                path
            };
            self.status = match export_text(&path, self.text.trim(), extension == "odt") {
                Ok(()) => format!("已儲存至 {}", path.display()),
                Err(error) => format!("儲存失敗：{error:#}"),
            };
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        self.update_events(ctx);
        // Keep polling while hidden because a hidden winit window may defer redraws.
        if self.state == State::Selecting {
            ctx.request_repaint_after(Duration::from_millis(75));
        }
        let hotkey = ctx.input_mut(|i| {
            i.consume_key(egui::Modifiers::NONE, egui::Key::F2)
                || i.consume_key(egui::Modifiers::CTRL, egui::Key::N)
        });

        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal_wrapped(|ui| {
                let snip = ui.add_enabled(
                    self.state == State::Idle,
                    egui::Button::new("開始框選 (F2)"),
                );
                if self.state == State::Idle && (snip.clicked() || hotkey) {
                    self.start_capture(ctx, frame);
                }
                let has_text = !self.text.trim().is_empty();
                for (label, ext) in [("另存 TXT", "txt"), ("另存 ODT", "odt")] {
                    if ui.add_enabled(has_text, egui::Button::new(label)).clicked() {
                        self.save(ext);
                    }
                }
                if ui
                    .add_enabled(has_text, egui::Button::new("複製文字"))
                    .clicked()
                {
                    ctx.copy_text(self.text.trim().to_owned());
                    self.status = "已複製到剪貼簿".into();
                }
                if ui
                    .add_enabled(self.state == State::Idle, egui::Button::new("清空內容"))
                    .clicked()
                {
                    self.text.clear();
                    self.preview = None;
                    self.status = "已清空內容".into();
                }
                if ui
                    .checkbox(&mut self.force_traditional, "強制轉繁體中文")
                    .changed()
                    && self.force_traditional
                    && has_text
                {
                    self.text = traditional(&self.text);
                    self.status = "已將目前文字轉成繁體中文".into();
                }
            });
        });

        egui::TopBottomPanel::bottom("status").show(ctx, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.label(format!("字數 {}", self.text.trim().chars().count()));
                ui.separator();
                if self.state == State::Recognizing {
                    ui.spinner();
                }
                ui.label(&self.status);
            });
        });

        egui::SidePanel::left("preview")
            .resizable(true)
            .default_width(285.0)
            .show(ctx, |ui| {
                ui.heading("截圖預覽");
                ui.separator();
                if let Some(preview) = &self.preview {
                    ui.add(egui::Image::from_texture(preview).max_size(ui.available_size()));
                } else {
                    ui.label("點擊「開始框選」以擷取圖片。");
                }
            });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("辨識結果");
            ui.separator();
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.add_sized(
                    ui.available_size(),
                    egui::TextEdit::multiline(&mut self.text)
                        .desired_width(f32::INFINITY)
                        .hint_text("辨識後可在此編輯文字"),
                );
            });
        });
    }
}

fn main() -> eframe::Result {
    unsafe {
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    }
    eframe::run_native(
        "剪取與 OCR 辨識工具",
        eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_inner_size([900.0, 640.0])
                .with_min_inner_size([720.0, 500.0]),
            ..Default::default()
        },
        Box::new(|cc| Ok(Box::new(App::new(&cc.egui_ctx)))),
    )
}
