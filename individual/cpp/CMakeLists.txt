cmake_minimum_required(VERSION 3.16)
project(individual LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCL REQUIRED)

add_executable(app main.cpp)
target_link_libraries(app PRIVATE OpenCL::OpenCL)
