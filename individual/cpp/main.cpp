#include <OpenCL/opencl.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include "external/json.hpp"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;

// =====================================================
// Konfigūracija (TCP)
// -----------------------------------------------------
// Naudojam 2 TCP jungtis:
//   - 5000: C++ -> Python (užduotys / payload’ai)
//   - 5001: Python -> C++ (rezultatai, stream’inami)
// =====================================================
static constexpr const char* kHost = "127.0.0.1";
static constexpr int kPortTasks    = 5000;
static constexpr int kPortResults  = 5001;

// =====================================================
// Duomenų struktūra – vienas įrašas iš JSON
// =====================================================
struct Record {
    std::string name;
    int games{};
    double winning{};
};

// =====================================================
// Minimalus RAII wrapper’is socket FD’ui
// -----------------------------------------------------
// Kad close() įvyktų automatiškai net jei išmesta exception.
// =====================================================
// class SocketFd {
// public:
//     SocketFd() = default;
//     explicit SocketFd(int fd) : fd_(fd) {}
//     ~SocketFd() { reset(); }

//     SocketFd(const SocketFd&) = delete;
//     SocketFd& operator=(const SocketFd&) = delete;

//     SocketFd(SocketFd&& other) noexcept : fd_(other.fd_) { other.fd_ = -1; }
//     SocketFd& operator=(SocketFd&& other) noexcept {
//         if (this != &other) {
//             reset();
//             fd_ = other.fd_;
//             other.fd_ = -1;
//         }
//         return *this;
//     }

//     int get() const { return fd_; }
//     bool valid() const { return fd_ >= 0; }

//     void reset(int new_fd = -1) {
//         if (fd_ >= 0) close(fd_);
//         fd_ = new_fd;
//     }

// private:
//     int fd_ = -1;
// };

// =====================================================
// Nuskaityti tekstinį failą (OpenCL kernel.cl)
// =====================================================
static std::string load_text_file(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) throw std::runtime_error("Cannot open file: " + path);

    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

// =====================================================
// TCP helperiai (line-based protokolas)
// -----------------------------------------------------
// TCP yra STREAM, todėl mes patys “susirėminam” eilutėmis:
//
// recv_line: skaito po 1 baitą, kol randa '\n'
// send_all : garantuoja, kad išsiųs VISĄ string’ą
// strip_newline: patogiai nuima \n/\r nuo galo
// =====================================================
static std::string recv_line(int sock) {
    std::string line;
    char c = 0;

    while (true) {
        ssize_t r = recv(sock, &c, 1, 0);
        if (r <= 0) {
            throw std::runtime_error("Socket disconnected while reading");
        }
        line.push_back(c);
        if (c == '\n') break;
    }
    return line;
}

static void send_all(int sock, const std::string& s) {
    // grąžina rodyklę į vidinį string buffer (c stiliaus txt, nes send yra c funkcija)
    const char* p = s.c_str();
    size_t left = s.size();

    while (left > 0) {
        ssize_t w = send(sock, p, left, 0);
        if (w <= 0) throw std::runtime_error("send() failed");
        p += w;
        left -= static_cast<size_t>(w);
    }
}

static std::string strip_newline(std::string s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
    return s;
}

// =====================================================
// OpenCL rezultatai (ką grąžina GPU skaičiavimas)
// =====================================================
struct OpenCLResult {
    std::vector<uint32_t> vals; // vienas rezultatas kiekvienam įrašui
    std::string device_str;     // platforma + device pavadinimas
    double seconds = 0.0;       // kernel vykdymo laikas
};

// =====================================================
// OpenCL vykdymas (GPU)
// -----------------------------------------------------
// - paruošia masyvus (games, winning)
// - sukuria GPU buferius
// - sukompiliuoja kernel.cl
// - paleidžia kernelį f_cl
// - nuskaito rezultatus atgal
// =====================================================
static OpenCLResult run_opencl(const std::vector<Record>& recs, uint32_t rounds) {
    OpenCLResult res;
    if (recs.empty()) return res;

    cl_int err = CL_SUCCESS;

    // 1) Platformos
    cl_uint pcount = 0;
    clGetPlatformIDs(0, nullptr, &pcount);
    std::vector<cl_platform_id> plats(pcount);
    clGetPlatformIDs(pcount, plats.data(), nullptr);

    // 2) GPU device (pirmas rastas)
    cl_device_id dev = nullptr;
    cl_platform_id chosen_plat = nullptr;
    for (auto p : plats) {
        cl_uint dcount = 0;
        if (clGetDeviceIDs(p, CL_DEVICE_TYPE_GPU, 0, nullptr, &dcount) == CL_SUCCESS && dcount > 0) {
            std::vector<cl_device_id> devs(dcount);
            clGetDeviceIDs(p, CL_DEVICE_TYPE_GPU, dcount, devs.data(), nullptr);
            dev = devs[0];
            chosen_plat = p;
            break;
        }
    }
    if (!dev) throw std::runtime_error("No OpenCL GPU device found.");

    // 3) Platform + device pavadinimai
    char pname[256]{}, dname[256]{};
    clGetPlatformInfo(chosen_plat, CL_PLATFORM_NAME, sizeof(pname), pname, nullptr);
    clGetDeviceInfo(dev, CL_DEVICE_NAME, sizeof(dname), dname, nullptr);
    res.device_str = std::string(pname) + " / " + std::string(dname);

    // 4) Context + queue
    cl_context ctx = clCreateContext(nullptr, 1, &dev, nullptr, nullptr, &err);
    cl_command_queue q = clCreateCommandQueue(ctx, dev, 0, &err);

    // 5) Host -> arrays
    const size_t n = recs.size();
    std::vector<int> games(n);
    std::vector<float> winning(n);
    for (size_t i = 0; i < n; i++) {
        games[i] = recs[i].games;
        winning[i] = static_cast<float>(recs[i].winning);
    }

    // 6) GPU buferiai
    cl_mem bufG = clCreateBuffer(ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                 sizeof(int) * n, games.data(), &err);
    cl_mem bufW = clCreateBuffer(ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                 sizeof(float) * n, winning.data(), &err);
    cl_mem bufO = clCreateBuffer(ctx, CL_MEM_WRITE_ONLY,
                                 sizeof(cl_uint) * n, nullptr, &err);

    // 7) Kernel source + build
    std::string src_str = load_text_file("cpp/kernel.cl");
    const char* src = src_str.c_str();
    size_t srclen = src_str.size();

    cl_program prog = clCreateProgramWithSource(ctx, 1, &src, &srclen, &err);
    err = clBuildProgram(prog, 1, &dev, nullptr, nullptr, nullptr);
    if (err != CL_SUCCESS) {
        size_t logsz = 0;
        clGetProgramBuildInfo(prog, dev, CL_PROGRAM_BUILD_LOG, 0, nullptr, &logsz);
        std::string log(logsz, '\0');
        clGetProgramBuildInfo(prog, dev, CL_PROGRAM_BUILD_LOG, logsz, log.data(), nullptr);
        throw std::runtime_error("OpenCL build failed:\n" + log);
    }

    cl_kernel k = clCreateKernel(prog, "f_cl", &err);

    // 8) Kernel argumentai
    cl_uint n_u = static_cast<cl_uint>(n);
    clSetKernelArg(k, 0, sizeof(cl_mem), &bufG);
    clSetKernelArg(k, 1, sizeof(cl_mem), &bufW);
    clSetKernelArg(k, 2, sizeof(cl_mem), &bufO);
    clSetKernelArg(k, 3, sizeof(cl_uint), &n_u);
    clSetKernelArg(k, 4, sizeof(cl_uint), &rounds);

    // 9) Paleidimas
    size_t global_items = n;
    if (const char* e = std::getenv("CL_ITEMS")) {
        size_t items = std::stoul(e);
        global_items = std::max<size_t>(1, std::min(items, n));
    }

    auto t0 = std::chrono::high_resolution_clock::now();
    clEnqueueNDRangeKernel(q, k, 1, nullptr, &global_items, nullptr, 0, nullptr, nullptr);
    clFinish(q);
    auto t1 = std::chrono::high_resolution_clock::now();
    res.seconds = std::chrono::duration<double>(t1 - t0).count();

    // 10) Nuskaitymas atgal
    res.vals.resize(n);
    clEnqueueReadBuffer(q, bufO, CL_TRUE, 0, sizeof(cl_uint) * n, res.vals.data(), 0, nullptr, nullptr);

    // 11) Cleanup
    clReleaseKernel(k);
    clReleaseProgram(prog);
    clReleaseMemObject(bufG);
    clReleaseMemObject(bufW);
    clReleaseMemObject(bufO);
    clReleaseCommandQueue(q);
    clReleaseContext(ctx);

    return res;
}

// =====================================================
// JSON nuskaitymas
// =====================================================
static std::vector<Record> read_records_json(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) throw std::runtime_error("Cannot open input file: " + path);

    json j;
    in >> j;

    std::vector<Record> records;
    records.reserve(j["player"].size());

    for (const auto& p : j["player"]) {
        records.push_back({
            p["name"].get<std::string>(),
            p["games"].get<int>(),
            p["winning"].get<double>()
        });
    }
    return records;
}

// =====================================================
// Filtrai (2 kriterijai)
// =====================================================
static bool filter1(const Record& r) { return r.games * r.winning >= 400.0; }
static bool filter2(const Record& r) { return r.winning >= 50.0; }

// =====================================================
// Prisijungimas prie host:port
// =====================================================
static int connect_tcp(const char* ip, int port) {
    // sukuriamas socket
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) throw std::runtime_error("socket() failed");

    sockaddr_in serv{};
    serv.sin_family = AF_INET;
    serv.sin_port = htons(port);

    // ip adreso konvertavimas -> 32 bits IPv4 address
    if (inet_pton(AF_INET, ip, &serv.sin_addr) != 1) {
        close(fd);
        throw std::runtime_error("inet_pton() failed");
    }

    // prisijungimas prie serverio
    if (connect(fd, (sockaddr*)&serv, sizeof(serv)) < 0) {
        std::string err = "connect() failed (port " + std::to_string(port) + "): " + strerror(errno);
        close(fd);
        throw std::runtime_error(err);
    }

    // grąžinu file descriptor
    return fd;
}

// =====================================================
// MAIN
// -----------------------------------------------------
// Pipeline:
//  1) Nuskaitom JSON
//  2) Atfiltruojam (2 kriterijai)
//  3) Prisijungiam prie Python (2 socketai)
//  4) Lygiagrečiai:
//      - OpenCL (GPU) skaičiavimas
//      - Siunčiam payload’us į Python (tasks socket)
//      - Priimam rezultatus iš Python (results socket)
//  5) Išvedam lenteles į failą
// =====================================================
int main(int argc, char** argv) {
    int sock_tasks = -1;
    int sock_results = -1;

    try {
        std::string input_path = "data/case4_mixed.json";
        std::string out_path   = "out/result.txt";
        uint32_t cl_rounds     = 600000;

        if (argc >= 2) input_path = argv[1];
        if (argc >= 3) out_path   = argv[2];
        if (argc >= 4) cl_rounds  = static_cast<uint32_t>(std::stoul(argv[3]));

        // 1) Nuskaitymas
        const auto all = read_records_json(input_path);
        std::cout << "Loaded records: " << all.size() << "\n";

        // 2) Filtravimas + minimalus payload Python’ui
        struct PyItem { int idx; std::string payload; std::string name; };

        std::vector<PyItem> to_py;
        std::vector<Record> to_opencl;

        for (const auto& r : all) {
            if (filter1(r) && filter2(r)) {
                std::ostringstream oss;
                oss << r.games << "," << r.winning;
                to_py.push_back({static_cast<int>(to_py.size()), oss.str(), r.name});
                to_opencl.push_back(r);
            }
        }

        // 3) Prisijungiam prie Python (2 jungtys)
        sock_tasks   = connect_tcp(kHost, kPortTasks);
        sock_results = connect_tcp(kHost, kPortResults);

        OpenCLResult clres;
        std::vector<uint32_t> py_vals;
        double py_seconds = 0.0;

        // Kad exception’ai iš threadų nedingtų
        std::exception_ptr ex_opencl = nullptr;
        std::exception_ptr ex_send   = nullptr;
        std::exception_ptr ex_recv   = nullptr;

        // 4) OpenCL thread (GPU)
        std::thread t_opencl([&] {
            try {
                clres = run_opencl(to_opencl, cl_rounds);
            } catch (...) {
                ex_opencl = std::current_exception();
            }
        });

        // 5) Receiver thread (Python results, stream)
        std::thread t_recv([&] {
            try {
                auto t0 = std::chrono::high_resolution_clock::now();

                // 5.1) Pirma eilutė privalo būti: "RESULTS n"
                std::string header = strip_newline(recv_line(sock_results));
                if (header.rfind("RESULTS ", 0) != 0) {
                    throw std::runtime_error("Bad header from python results socket: " + header);
                }

                int n = std::stoi(header.substr(std::string("RESULTS ").size()));
                py_vals.assign(n, 0);

                // 5.2) Toliau stream: "idx;val" ... "DONE"
                while (true) {
                    std::string line = strip_newline(recv_line(sock_results));
                    if (line == "DONE") break;

                    auto p = line.find(';');
                    if (p == std::string::npos) continue;

                    int idx = std::stoi(line.substr(0, p));
                    uint32_t val = static_cast<uint32_t>(std::stoul(line.substr(p + 1)));

                    if (idx >= 0 && idx < n) {
                        py_vals[idx] = val;
                    }
                }

                auto t1 = std::chrono::high_resolution_clock::now();
                py_seconds = std::chrono::duration<double>(t1 - t0).count();
            } catch (...) {
                ex_recv = std::current_exception();
            }
        });

        // 6) Sender thread (tasks į Python, po vieną eilutę)
        std::thread t_send([&] {
            try {
                // 6.1) Pradžia: "BEGIN n"
                send_all(sock_tasks, "BEGIN " + std::to_string(to_py.size()) + "\n");

                // 6.2) Stream’inam tasks: "idx;payload"
                for (const auto& it : to_py) {
                    send_all(sock_tasks, std::to_string(it.idx) + ";" + it.payload + "\n");
                }

                // 6.3) Pabaiga: "END"
                send_all(sock_tasks, "END\n");
            } catch (...) {
                ex_send = std::current_exception();
            }
        });

        // 7) Palaukiam visų threadų
        t_send.join();
        t_recv.join();
        t_opencl.join();

        // 8) Jei buvo error’as kuriame nors threade
        if (ex_send)   std::rethrow_exception(ex_send);
        if (ex_recv)   std::rethrow_exception(ex_recv);
        if (ex_opencl) std::rethrow_exception(ex_opencl);

        // 9) Rezultatų išvedimas
        std::filesystem::create_directories("out");
        std::ofstream out(out_path);
        if (!out.is_open()) throw std::runtime_error("Cannot open output file: " + out_path);

        auto print_sep3 = [&](int w1, int w2, int w3) {
            out << std::string(w1, '-') << "+" << std::string(w2, '-') << "+" << std::string(w3, '-') << "\n";
        };
        auto print_row3 = [&](int w1, int w2, int w3, const std::string& c1, const std::string& c2, const std::string& c3) {
            out << std::left << std::setw(w1) << c1 << "|"
                << std::left << std::setw(w2) << c2 << "|"
                << std::left << std::setw(w3) << c3 << "\n";
        };

        auto print_sep5 = [&](int w1, int w2, int w3, int w4, int w5) {
            out << std::string(w1, '-') << "+"
                << std::string(w2, '-') << "+"
                << std::string(w3, '-') << "+"
                << std::string(w4, '-') << "+"
                << std::string(w5, '-') << "\n";
        };
        auto print_row5 = [&](int w1, int w2, int w3, int w4, int w5,
                              const std::string& c1, const std::string& c2, const std::string& c3,
                              const std::string& c4, const std::string& c5) {
            out << std::left << std::setw(w1) << c1 << "|"
                << std::left << std::setw(w2) << c2 << "|"
                << std::left << std::setw(w3) << c3 << "|"
                << std::left << std::setw(w4) << c4 << "|"
                << std::left << std::setw(w5) << c5 << "\n";
        };

        out << "OpenCL device: " << clres.device_str << "\n";
        out << "OpenCL time: " << clres.seconds << " s\n";
        out << "Python time: " << py_seconds << " s\n\n";

        const int W_NAME = 22, W_G = 10, W_W = 14, W_CL = 18, W_PY = 18;

        out << "RESULTS (filtered) - OpenCL and Python separately\n";
        size_t n_final = std::min({to_opencl.size(), clres.vals.size(), py_vals.size()});
        size_t dropped = to_opencl.size() - n_final;

        print_sep5(W_NAME, W_G, W_W, W_CL, W_PY);
        print_row5(W_NAME, W_G, W_W, W_CL, W_PY, "name", "games", "winning", "opencl_val", "python_val");
        print_sep5(W_NAME, W_G, W_W, W_CL, W_PY);

        for (size_t i = 0; i < n_final; i++) {
            const auto& r = to_opencl[i];
            std::ostringstream sg, sw, scl, spy;
            sg << r.games;
            sw << std::fixed << std::setprecision(3) << r.winning;
            scl << clres.vals[i];
            spy << py_vals[i];
            print_row5(W_NAME, W_G, W_W, W_CL, W_PY, r.name, sg.str(), sw.str(), scl.str(), spy.str());
        }

        print_sep5(W_NAME, W_G, W_W, W_CL, W_PY);
        if (dropped > 0) out << "\nWARNING: dropped " << dropped << " rows due to missing results\n";
        out << "\n";

        out << "STARTING DATA (all records)\n";
        print_sep3(W_NAME, W_G, W_W);
        print_row3(W_NAME, W_G, W_W, "name", "games", "winning");
        print_sep3(W_NAME, W_G, W_W);

        for (const auto& r : all) {
            std::ostringstream sg, sw;
            sg << r.games;
            sw << std::fixed << std::setprecision(3) << r.winning;
            print_row3(W_NAME, W_G, W_W, r.name, sg.str(), sw.str());
        }
        print_sep3(W_NAME, W_G, W_W);

        std::cout << "Wrote " << out_path << "\n";
        std::cout << "OpenCL device: " << clres.device_str << "\n";

        close(sock_tasks);
        close(sock_results);
        
        return 0;

    } catch (const std::exception& e) {
        std::cerr << "FATAL: " << e.what() << "\n";
        
        if (sock_tasks >= 0) close(sock_tasks);
        if (sock_results >= 0) close(sock_results);

        return 1;
    }
}
