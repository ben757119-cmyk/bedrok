#include <Windows.h>
#include <thread>
#include <atomic>
#include <fstream>
#include <sstream>
#include "module_manager.h"
#include "overlay.h"

static std::atomic<bool> g_run{false};
static HMODULE g_mod = nullptr;

static void log_msg(const char* s) {
    std::ofstream f("C:\\Users\\Public\\bedrok.log", std::ios::app);
    f << s << "\n";
}

static std::wstring to_wide(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, &w[0], n);
    if (!w.empty() && w.back() == 0) w.pop_back();
    return w;
}

static void refresh_overlay() {
    std::vector<OverlayLine> lines;
    lines.push_back({L"bedROK", RGB(100, 200, 255)});
    lines.push_back({L"F1-F5 toggle modules", RGB(140, 140, 150)});

    SYSTEMTIME st{};
    GetLocalTime(&st);
    if (ModuleManager::instance().find("clock") &&
        ModuleManager::instance().find("clock")->enabled) {
        wchar_t buf[64];
        swprintf_s(buf, L"%02d:%02d:%02d", st.wHour, st.wMinute, st.wSecond);
        lines.push_back({buf, RGB(200, 200, 210)});
    }

    if (ModuleManager::instance().find("arraylist") &&
        ModuleManager::instance().find("arraylist")->enabled) {
        for (auto& m : ModuleManager::instance().all()) {
            if (!m->enabled) continue;
            if (m->id == "arraylist" || m->id == "watermark") continue;
            lines.push_back({to_wide(m->name), RGB(160, 230, 180)});
        }
    }

    Overlay::instance().set_lines(std::move(lines));
}

static void client_main() {
    log_msg("bedROK loaded (safe modules only)");
    register_safe_modules();
    Overlay::instance().start(g_mod);
    ModuleManager::instance().set("watermark", true);
    ModuleManager::instance().set("arraylist", true);
    refresh_overlay();

    while (g_run.load()) {
        if (GetAsyncKeyState(VK_F1) & 1) ModuleManager::instance().toggle("fullbright");
        if (GetAsyncKeyState(VK_F2) & 1) ModuleManager::instance().toggle("crosshair");
        if (GetAsyncKeyState(VK_F3) & 1) ModuleManager::instance().toggle("clock");
        if (GetAsyncKeyState(VK_F4) & 1) ModuleManager::instance().toggle("arraylist");
        if (GetAsyncKeyState(VK_F5) & 1) ModuleManager::instance().toggle("watermark");

        ModuleManager::instance().tick();
        refresh_overlay();
        Sleep(50);
    }

    ModuleManager::instance().set("fullbright", false);
    Overlay::instance().stop();
    log_msg("bedROK unloaded");
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        g_mod = h;
        g_run = true;
        std::thread(client_main).detach();
    } else if (reason == DLL_PROCESS_DETACH) {
        g_run = false;
        Sleep(100);
        ModuleManager::instance().set("fullbright", false);
    }
    return TRUE;
}
