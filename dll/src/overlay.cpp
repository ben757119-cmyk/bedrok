#include "overlay.h"
#include <string>

Overlay& Overlay::instance() {
    static Overlay o;
    return o;
}

void Overlay::start(HINSTANCE inst) {
    if (hwnd_) return;
    if (!cs_init_) { InitializeCriticalSection(&cs_); cs_init_ = true; }

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = inst;
    wc.lpszClassName = L"BedrokOverlay";
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    RegisterClassExW(&wc);

    hwnd_ = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
        L"BedrokOverlay", L"bedROK",
        WS_POPUP,
        20, 20, 420, 280,
        nullptr, nullptr, inst, nullptr);

    if (!hwnd_) return;
    SetLayeredWindowAttributes(hwnd_, RGB(0, 0, 0), 0, LWA_COLORKEY);
    ShowWindow(hwnd_, SW_SHOWNOACTIVATE);
}

void Overlay::stop() {
    if (hwnd_) {
        DestroyWindow(hwnd_);
        hwnd_ = nullptr;
    }
}

void Overlay::set_lines(std::vector<OverlayLine> lines) {
    if (!cs_init_) return;
    EnterCriticalSection(&cs_);
    lines_ = std::move(lines);
    LeaveCriticalSection(&cs_);
    if (hwnd_) InvalidateRect(hwnd_, nullptr, TRUE);
}

void Overlay::set_crosshair(bool on) {
    crosshair_ = on;
    if (hwnd_) InvalidateRect(hwnd_, nullptr, TRUE);
}

void Overlay::paint(HDC hdc) {
    RECT rc{};
    GetClientRect(hwnd_, &rc);
    HBRUSH bg = CreateSolidBrush(RGB(0, 0, 0));
    FillRect(hdc, &rc, bg);
    DeleteObject(bg);

    SetBkMode(hdc, TRANSPARENT);
    HFONT font = CreateFontW(18, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    HFONT old = (HFONT)SelectObject(hdc, font);

    EnterCriticalSection(&cs_);
    int y = 12;
    for (auto& line : lines_) {
        SetTextColor(hdc, line.color);
        TextOutW(hdc, 14, y, line.text.c_str(), (int)line.text.size());
        y += 22;
    }
    LeaveCriticalSection(&cs_);

    if (crosshair_) {
        int cx = rc.right / 2, cy = rc.bottom / 2;
        HPEN pen = CreatePen(PS_SOLID, 2, RGB(120, 220, 255));
        HGDIOBJ op = SelectObject(hdc, pen);
        MoveToEx(hdc, cx - 10, cy, nullptr); LineTo(hdc, cx + 10, cy);
        MoveToEx(hdc, cx, cy - 10, nullptr); LineTo(hdc, cx, cy + 10);
        SelectObject(hdc, op);
        DeleteObject(pen);
    }

    SelectObject(hdc, old);
    DeleteObject(font);
}

LRESULT CALLBACK Overlay::WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    Overlay& self = Overlay::instance();
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);
        self.paint(hdc);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_DESTROY:
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}
