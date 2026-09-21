#include "module_manager.h"
#include "overlay.h"
#include <Windows.h>
#include <vector>
#include <cmath>

struct FullbrightModule : Module {
    WORD backup_[3][256]{};
    bool have_backup_ = false;

    FullbrightModule() { id = "fullbright"; name = "Fullbright"; }

    void on_enable() override {
        HDC hdc = GetDC(nullptr);
        if (!hdc) return;
        if (GetDeviceGammaRamp(hdc, backup_)) have_backup_ = true;
        WORD ramp[3][256];
        for (int i = 0; i < 256; i++) {
            double t = i / 255.0;
            double b = pow(t, 0.65);
            WORD w = (WORD)(b * 65535.0);
            ramp[0][i] = ramp[1][i] = ramp[2][i] = w;
        }
        SetDeviceGammaRamp(hdc, ramp);
        ReleaseDC(nullptr, hdc);
    }

    void on_disable() override {
        if (!have_backup_) return;
        HDC hdc = GetDC(nullptr);
        if (hdc) {
            SetDeviceGammaRamp(hdc, backup_);
            ReleaseDC(nullptr, hdc);
        }
        have_backup_ = false;
    }
};

struct CrosshairModule : Module {
    CrosshairModule() { id = "crosshair"; name = "Crosshair"; }
    void on_enable() override { Overlay::instance().set_crosshair(true); }
    void on_disable() override { Overlay::instance().set_crosshair(false); }
};

struct WatermarkModule : Module {
    WatermarkModule() { id = "watermark"; name = "Watermark"; enabled = true; }
};

struct ArrayListModule : Module {
    ArrayListModule() { id = "arraylist"; name = "Array list"; enabled = true; }
};

struct ClockModule : Module {
    ClockModule() { id = "clock"; name = "Clock"; }
};

void register_safe_modules() {
    auto& mm = ModuleManager::instance();
    mm.add(std::make_unique<WatermarkModule>());
    mm.add(std::make_unique<ArrayListModule>());
    mm.add(std::make_unique<FullbrightModule>());
    mm.add(std::make_unique<CrosshairModule>());
    mm.add(std::make_unique<ClockModule>());
}
