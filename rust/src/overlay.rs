use std::{
    mem::{size_of, zeroed},
    ptr::null_mut,
};

use anyhow::{Result, ensure};
use image::{Rgb, RgbImage};
use windows_sys::{
    Win32::{
        Foundation::{HWND, LPARAM, LRESULT, POINT, RECT, WPARAM},
        Graphics::Gdi::*,
        System::LibraryLoader::GetModuleHandleW,
        UI::{
            Input::KeyboardAndMouse::{SetCapture, VK_ESCAPE},
            WindowsAndMessaging::*,
        },
    },
    core::w,
};

struct Desktop {
    bounds: RECT,
    info: BITMAPINFO,
    pixels: Vec<u8>,
}

impl Desktop {
    fn capture() -> Result<Self> {
        // All coordinates and the top-down DIB use physical pixels.
        unsafe {
            let x = GetSystemMetrics(SM_XVIRTUALSCREEN);
            let y = GetSystemMetrics(SM_YVIRTUALSCREEN);
            let width = GetSystemMetrics(SM_CXVIRTUALSCREEN);
            let height = GetSystemMetrics(SM_CYVIRTUALSCREEN);
            ensure!(width > 0 && height > 0, "無法取得螢幕尺寸");

            let mut pixels = vec![0; width as usize * height as usize * 4];
            let mut info: BITMAPINFO = zeroed();
            info.bmiHeader = BITMAPINFOHEADER {
                biSize: size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: width,
                biHeight: -height,
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB,
                ..zeroed()
            };
            let screen = GetDC(null_mut());
            ensure!(!screen.is_null(), "無法讀取桌面");
            let memory = CreateCompatibleDC(screen);
            let bitmap = CreateCompatibleBitmap(screen, width, height);
            let mut captured = false;
            if !memory.is_null() && !bitmap.is_null() {
                let original = SelectObject(memory, bitmap);
                if !original.is_null() {
                    let copied = BitBlt(
                        memory,
                        0,
                        0,
                        width,
                        height,
                        screen,
                        x,
                        y,
                        SRCCOPY | CAPTUREBLT,
                    );
                    SelectObject(memory, original);
                    captured = copied != 0
                        && GetDIBits(
                            screen,
                            bitmap,
                            0,
                            height as u32,
                            pixels.as_mut_ptr().cast(),
                            &mut info,
                            DIB_RGB_COLORS,
                        ) == height;
                }
            }
            if !bitmap.is_null() {
                DeleteObject(bitmap);
            }
            if !memory.is_null() {
                DeleteDC(memory);
            }
            ReleaseDC(null_mut(), screen);
            ensure!(captured, "擷取桌面失敗");
            Ok(Self {
                bounds: RECT {
                    left: x,
                    top: y,
                    right: x + width,
                    bottom: y + height,
                },
                info,
                pixels,
            })
        }
    }

    fn crop(&self, rect: RECT) -> Option<RgbImage> {
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        if width <= 8 || height <= 8 {
            return None;
        }
        Some(RgbImage::from_fn(width as u32, height as u32, |x, y| {
            let stride = self.info.bmiHeader.biWidth as usize;
            let index =
                ((rect.top as usize + y as usize) * stride + rect.left as usize + x as usize) * 4;
            Rgb([
                self.pixels[index + 2],
                self.pixels[index + 1],
                self.pixels[index],
            ])
        }))
    }
}

struct Selection {
    desktop: Desktop,
    dim: Vec<u8>,
    start: Option<POINT>,
    end: POINT,
    result: Option<RECT>,
}

impl Selection {
    fn rect(&self) -> Option<RECT> {
        let start = self.start?;
        Some(RECT {
            left: start.x.min(self.end.x),
            top: start.y.min(self.end.y),
            right: start.x.max(self.end.x),
            bottom: start.y.max(self.end.y),
        })
    }

    fn point(&self, hwnd: HWND, lparam: LPARAM) -> POINT {
        let mut point = POINT {
            x: (lparam as i16).into(),
            y: ((lparam >> 16) as i16).into(),
        };
        unsafe {
            let mut screen = POINT::default();
            if GetCursorPos(&mut screen) != 0 && ScreenToClient(hwnd, &mut screen) != 0 {
                point = screen;
            }
        }
        point.x = point.x.clamp(0, self.desktop.info.bmiHeader.biWidth);
        point.y = point.y.clamp(0, -self.desktop.info.bmiHeader.biHeight);
        point
    }

    fn paint(&self, hwnd: HWND) {
        unsafe {
            let mut paint: PAINTSTRUCT = zeroed();
            let dc = BeginPaint(hwnd, &mut paint);
            let width = self.desktop.info.bmiHeader.biWidth;
            let height = -self.desktop.info.bmiHeader.biHeight;
            let draw = |pixels: &[u8]| {
                SetDIBitsToDevice(
                    dc,
                    0,
                    0,
                    width as u32,
                    height as u32,
                    0,
                    0,
                    0,
                    height as u32,
                    pixels.as_ptr().cast(),
                    &self.desktop.info,
                    DIB_RGB_COLORS,
                );
            };
            draw(&self.dim);
            if let Some(rect) = self.rect() {
                let saved = SaveDC(dc);
                if saved != 0 {
                    IntersectClipRect(dc, rect.left, rect.top, rect.right, rect.bottom);
                    draw(&self.desktop.pixels);
                    RestoreDC(dc, saved);
                }
                SetDCBrushColor(dc, 0x00ff_b000);
                FrameRect(dc, &rect, GetStockObject(DC_BRUSH));
            }
            let mut hint = RECT {
                left: -self.desktop.bounds.left,
                top: 20 - self.desktop.bounds.top,
                right: GetSystemMetrics(SM_CXSCREEN) - self.desktop.bounds.left,
                bottom: 60 - self.desktop.bounds.top,
            };
            SetBkMode(dc, TRANSPARENT as i32);
            SetTextColor(dc, 0x00ff_ffff);
            DrawTextW(
                dc,
                w!("拖曳滑鼠左鍵框選文字區域    ｜    Esc 取消"),
                -1,
                &mut hint,
                DT_CENTER | DT_VCENTER | DT_SINGLELINE,
            );
            EndPaint(hwnd, &paint);
        }
    }
}

unsafe extern "system" fn window_proc(
    hwnd: HWND,
    message: u32,
    key: WPARAM,
    data: LPARAM,
) -> LRESULT {
    // User data points to the stack-owned Selection for the lifetime of this window.
    unsafe {
        if message == WM_NCCREATE {
            let create = &*(data as *const CREATESTRUCTW);
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, create.lpCreateParams as isize);
            return DefWindowProcW(hwnd, message, key, data);
        }
        let selection = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut Selection;
        if selection.is_null() {
            return DefWindowProcW(hwnd, message, key, data);
        }
        match message {
            WM_PAINT => (*selection).paint(hwnd),
            WM_LBUTTONDOWN => {
                let point = (*selection).point(hwnd, data);
                (*selection).start = Some(point);
                (*selection).end = point;
                SetCapture(hwnd);
                InvalidateRect(hwnd, null_mut(), 0);
            }
            WM_MOUSEMOVE if (*selection).start.is_some() => {
                (*selection).end = (*selection).point(hwnd, data);
                InvalidateRect(hwnd, null_mut(), 0);
            }
            WM_LBUTTONUP => {
                (*selection).end = (*selection).point(hwnd, data);
                (*selection).result = (*selection).rect();
                (*selection).start = None;
                DestroyWindow(hwnd);
            }
            WM_KEYDOWN if key == VK_ESCAPE as usize => {
                DestroyWindow(hwnd);
            }
            WM_CLOSE | WM_DISPLAYCHANGE => {
                DestroyWindow(hwnd);
            }
            WM_CANCELMODE => {
                PostMessageW(hwnd, WM_CLOSE, 0, 0);
            }
            WM_CAPTURECHANGED if (*selection).start.is_some() => {
                (*selection).start = None;
                PostMessageW(hwnd, WM_CLOSE, 0, 0);
            }
            WM_DESTROY => {
                PostQuitMessage(0);
            }
            _ => return DefWindowProcW(hwnd, message, key, data),
        }
        0
    }
}

pub fn select_region() -> Result<Option<RgbImage>> {
    let desktop = Desktop::capture()?;
    let dim = desktop.pixels.iter().map(|channel| channel / 2).collect();
    let mut selection = Selection {
        desktop,
        dim,
        start: None,
        end: POINT::default(),
        result: None,
    };
    let bounds = selection.desktop.bounds;

    unsafe {
        let instance = GetModuleHandleW(null_mut());
        let class = w!("SnippingOcrSelection");
        let descriptor = WNDCLASSW {
            lpfnWndProc: Some(window_proc),
            hInstance: instance,
            hCursor: LoadCursorW(null_mut(), IDC_CROSS),
            lpszClassName: class,
            ..zeroed()
        };
        ensure!(RegisterClassW(&descriptor) != 0, "無法註冊框選視窗");
        let window = CreateWindowExW(
            WS_EX_TOPMOST,
            class,
            w!("框選 OCR 區域"),
            WS_POPUP,
            bounds.left,
            bounds.top,
            bounds.right - bounds.left,
            bounds.bottom - bounds.top,
            null_mut(),
            null_mut(),
            instance,
            (&mut selection as *mut Selection).cast(),
        );
        if window.is_null() {
            UnregisterClassW(class, instance);
            anyhow::bail!("無法開啟框選視窗");
        }
        ShowWindow(window, SW_SHOW);
        SetForegroundWindow(window);
        UpdateWindow(window);
        let mut message: MSG = zeroed();
        loop {
            let read = GetMessageW(&mut message, null_mut(), 0, 0);
            if read <= 0 {
                if read < 0 {
                    DestroyWindow(window);
                }
                UnregisterClassW(class, instance);
                ensure!(read == 0, "框選視窗意外停止");
                break;
            }
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }

    Ok(selection
        .result
        .and_then(|rect| selection.desktop.crop(rect)))
}
