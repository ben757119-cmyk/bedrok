#pragma once
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>

struct Module {
    std::string id;
    std::string name;
    bool enabled = false;
    virtual ~Module() = default;
    virtual void on_enable() {}
    virtual void on_disable() {}
    virtual void on_tick() {}
};

class ModuleManager {
public:
    static ModuleManager& instance();
    void add(std::unique_ptr<Module> m);
    Module* find(const std::string& id);
    void set(const std::string& id, bool on);
    void toggle(const std::string& id);
    void tick();
    const std::vector<std::unique_ptr<Module>>& all() const { return mods_; }
private:
    std::vector<std::unique_ptr<Module>> mods_;
};

void register_safe_modules();
