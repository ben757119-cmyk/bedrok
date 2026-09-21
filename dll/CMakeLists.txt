cmake_minimum_required(VERSION 3.20)
project(bedrok_dll LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
add_library(client SHARED
  src/dllmain.cpp
  src/module_manager.cpp
  src/modules.cpp
  src/overlay.cpp
)
target_include_directories(client PRIVATE include)
target_compile_definitions(client PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(client PRIVATE user32 gdi32)
set_target_properties(client PROPERTIES OUTPUT_NAME "bedrok")
