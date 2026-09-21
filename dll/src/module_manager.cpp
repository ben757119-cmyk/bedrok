#include "module_manager.h"

ModuleManager& ModuleManager::instance() {
    static ModuleManager m;
    return m;
}

void ModuleManager::add(std::unique_ptr<Module> m) { mods_.push_back(std::move(m)); }

Module* ModuleManager::find(const std::string& id) {
    for (auto& m : mods_) if (m->id == id) return m.get();
    return nullptr;
}

void ModuleManager::set(const std::string& id, bool on) {
    Module* m = find(id);
    if (!m || m->enabled == on) return;
    m->enabled = on;
    if (on) m->on_enable(); else m->on_disable();
}

void ModuleManager::toggle(const std::string& id) {
    Module* m = find(id);
    if (m) set(id, !m->enabled);
}

void ModuleManager::tick() {
    for (auto& m : mods_) if (m->enabled) m->on_tick();
}
