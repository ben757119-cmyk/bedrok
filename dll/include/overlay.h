#pragma once
#include <Windows.h>
#include <string>
#include <vector>

struct OverlayLine {
    std::wstring text;
    COLORREF color;
};

class Overlay {
public:
    static Overlay& instance();
    void start(HINSTANCE inst);
    void stop();
    void set_lines(std::vector<OverlayLine> lines);
    void set_crosshair(bool on);
    bool running() const { return hwnd_ != nullptr; }
private:
    Overlay() = default;
    static LRESULT CALLBACK WndProc(HWND, UINT, WPARAM, LPARAM);
    void paint(HDC hdc);
    HWND hwnd_ = nullptr;
    std::vector<OverlayLine> lines_;
    bool crosshair_ = false;
    CRITICAL_SECTION cs_{};
    bool cs_init_ = false;
};
