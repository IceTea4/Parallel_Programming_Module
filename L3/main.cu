#include <cuda_runtime.h>
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <algorithm>
#include <nlohmann/json.hpp>

using json = nlohmann::json;
using namespace std;

constexpr int MAX_NAME_LEN   = 64;
constexpr int MAX_RESULT_LEN = 64;

// Paprastas klaidoms tikrinti
#define CUDA_CHECK(call)                                                 \
    do {                                                                 \
        cudaError_t err = call;                                          \
        if (err != cudaSuccess) {                                        \
            cerr << "CUDA error: " << cudaGetErrorString(err)            \
                 << " (" << __FILE__ << ":" << __LINE__ << ")" << endl;  \
            exit(EXIT_FAILURE);                                          \
        }                                                                \
    } while (0)

__device__ char winning_to_grade(float w) {
    if (w >= 90.0f) return 'A';
    if (w >= 80.0f) return 'B';
    if (w >= 70.0f) return 'C';
    if (w >= 60.0f) return 'D';
    return 'E';
}

__device__ int int_to_str(int value, char* out) {
    int pos = 0;

    if (value == 0) {
        out[0] = '0';
        return 1;
    }

    bool neg = value < 0;
    if (neg) value = -value;

    char tmp[12];
    int t = 0;
    while (value > 0) {
        tmp[t++] = '0' + (value % 10);
        value /= 10;
    }

    if (neg) out[pos++] = '-';

    for (int i = t - 1; i >= 0; --i) {
        out[pos++] = tmp[i];
    }

    return pos;
}

__device__ void to_upper_copy(const char* src, char* dst, int maxLen) {
    int i = 0;
    for (; i < maxLen - 1 && src[i] != '\0'; ++i) {
        char c = src[i];
        if (c >= 'a' && c <= 'z') {
            c = c - 'a' + 'A';
        }
        dst[i] = c;
    }
    dst[i] = '\0';
}

__global__ void filter_players_kernel(
    const char* names,
    const int*  games,
    const float* winning,
    int count,
    char* results,
    int* resultCount
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int totalThreads = gridDim.x * blockDim.x;

    for (int idx = tid; idx < count; idx += totalThreads) {
        float w = winning[idx];
        int   g = games[idx];

        // sąlyga
        if (w >= 50.0f && g * w >= 400.0f) {

            // vietiniai buferiai rezultate formavimui
            char upperName[MAX_NAME_LEN];
            char localResult[MAX_RESULT_LEN];

            // pasiimame vardą (i-o įrašo pradžia)
            const char* namePtr = names + idx * MAX_NAME_LEN;
            to_upper_copy(namePtr, upperName, MAX_NAME_LEN);

            int pos = 0;
            // įrašome vardą
            for (int i = 0; i < MAX_NAME_LEN && upperName[i] != '\0'; ++i) {
                localResult[pos++] = upperName[i];
                if (pos >= MAX_RESULT_LEN - 1) break;
            }

            if (pos < MAX_RESULT_LEN - 1) localResult[pos++] = '-';

            // įrašome games skaičių
            if (pos < MAX_RESULT_LEN - 1) {
                pos += int_to_str(g, localResult + pos);
            }

            if (pos < MAX_RESULT_LEN - 1) localResult[pos++] = '-';

            // įrašome įvertinimo raidę pagal winning
            if (pos < MAX_RESULT_LEN - 1) {
                char grade = winning_to_grade(w);
                localResult[pos++] = grade;
            }

            // užpildome likusią dalį tarpais ir pridedame '\0'
            while (pos < MAX_RESULT_LEN - 1) {
                localResult[pos++] = ' ';
            }
            localResult[pos] = '\0';

            // pasiimame laisvą rezultato indeksą atomine operacija
            int outIndex = atomicAdd(resultCount, 1);

            if (outIndex < count) {
                for (int i = 0; i < MAX_RESULT_LEN; ++i) {
                    results[outIndex * MAX_RESULT_LEN + i] = localResult[i];
                }
            }
        }
    }
}

struct Player {
    string name;
    int    games;
    float  winning;
};

vector<Player> read_players_from_file(const string& path) {
    ifstream in(path);
    if (!in.is_open()) {
        cerr << "Nepavyko atidaryti failo: " << path << endl;
        exit(EXIT_FAILURE);
    }

    json j;
    in >> j;

    vector<Player> players;
    auto arr = j["player"];
    players.reserve(arr.size());

    for (const auto& p : arr) {
        Player pl;
        pl.name    = p["name"].get<string>();
        pl.games   = p["games"].get<int>();
        pl.winning = p["winning"].get<float>();
        players.push_back(pl);
    }

    return players;
}

void write_results_to_file(const string& path,
                           const vector<char>& results,
                           int count) {
    ofstream out(path);
    if (!out.is_open()) {
        cerr << "Nepavyko atidaryti rezultatų failo: " << path << endl;
        exit(EXIT_FAILURE);
    }

    for (int i = 0; i < count; ++i) {
        const char* line = results.data() + i * MAX_RESULT_LEN;

        // nuimame gale tarpus
        string s(line);
        while (!s.empty() && s.back() == ' ') {
            s.pop_back();
        }
        out << s << '\n';
    }
}

int main(int argc, char** argv) {
    if (argc < 3) {
        cerr << "Naudojimas: " << argv[0] << " input.json output.txt\n";
        return 1;
    }

    string inputPath  = argv[1];
    string outputPath = argv[2];

    // Nuskaityti duomenis iš JSON
    vector<Player> players = read_players_from_file(inputPath);
    int N = players.size();

    cout << "Nuskaityta " << N << " irasu." << endl;

    // Paruošti plokščius masyvus vardams, games ir winning
    vector<char>  h_names(N * MAX_NAME_LEN, 0);
    vector<int>   h_games(N);
    vector<float> h_winning(N);

    for (int i = 0; i < N; ++i) {
        string name = players[i].name;

        if (name.size() >= MAX_NAME_LEN)
        {
            name = name.substr(0, MAX_NAME_LEN - 1);
        }

        strcpy(&h_names[i * MAX_NAME_LEN], name.c_str());

        h_games[i]   = players[i].games;
        h_winning[i] = players[i].winning;
    }

    // CUDA atminties išskyrimas
    char*  d_names    = nullptr;
    int*   d_games    = nullptr;
    float* d_winning  = nullptr;
    char*  d_results  = nullptr;
    int*   d_resultCount = nullptr;

    // GPU atmintyje išskiria nurodytą kiekį atminties
    CUDA_CHECK(cudaMalloc(&d_names,   h_names.size()   * sizeof(char)));
    CUDA_CHECK(cudaMalloc(&d_games,   h_games.size()   * sizeof(int)));
    CUDA_CHECK(cudaMalloc(&d_winning, h_winning.size() * sizeof(float)));
    CUDA_CHECK(cudaMalloc(&d_results, N * MAX_RESULT_LEN * sizeof(char)));
    CUDA_CHECK(cudaMalloc(&d_resultCount, sizeof(int)));

    int zero = 0;
    // Kopijuoja duomenis tarp CPU ir GPU
    CUDA_CHECK(cudaMemcpy(d_names,   h_names.data(),
                          h_names.size() * sizeof(char),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_games,   h_games.data(),
                          h_games.size() * sizeof(int),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_winning, h_winning.data(),
                          h_winning.size() * sizeof(float),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_resultCount, &zero, sizeof(int),
                          cudaMemcpyHostToDevice));

    // Parenkame gijų tinklą pagal užduotį
    int threadsPerBlock = 96;
    int blocks = 2;
    int totalThreads = threadsPerBlock * blocks;

    if (totalThreads >= N) {
        blocks = max(2, N / 64);
        threadsPerBlock = 32;
    }

    cout << "Paleidziu kernel su " << blocks
         << " blokais ir " << threadsPerBlock
         << " gijomis bloke." << endl;

    // Kernel kvietimas
    filter_players_kernel<<<blocks, threadsPerBlock>>>(
        d_names, d_games, d_winning, N, d_results, d_resultCount
    );

    // Blokuoja CPU kodą, kol GPU pabaigs visą jam priskirtą darbą
    CUDA_CHECK(cudaDeviceSynchronize());

    // Ar buvo klaidų per paskutinį kernel paleidimą
    cudaError_t lastErr = cudaGetLastError();
    if (lastErr != cudaSuccess) {
        cerr << "Klaida po kernel vykdymo: "
             << cudaGetErrorString(lastErr) << endl;
        return 1;
    }

    // Nusikopijuojame rezultatų kiekį ir patį rezultatų masyvą (GPU -> CPU)
    int h_resultCount = 0;
    CUDA_CHECK(cudaMemcpy(&h_resultCount, d_resultCount, sizeof(int),
                          cudaMemcpyDeviceToHost));

    cout << "Atrinkta " << h_resultCount << " irasu." << endl;

    // GPU -> CPU resultatai
    vector<char> h_results(h_resultCount * MAX_RESULT_LEN);
    if (h_resultCount > 0) {
        CUDA_CHECK(cudaMemcpy(h_results.data(), d_results,
                              h_resultCount * MAX_RESULT_LEN * sizeof(char),
                              cudaMemcpyDeviceToHost));
    }

    // Išsaugome į tekstinį failą
    write_results_to_file(outputPath, h_results, h_resultCount);

    // Atlaisviname GPU atmintį
    CUDA_CHECK(cudaFree(d_names));
    CUDA_CHECK(cudaFree(d_games));
    CUDA_CHECK(cudaFree(d_winning));
    CUDA_CHECK(cudaFree(d_results));
    CUDA_CHECK(cudaFree(d_resultCount));

    cout << "Baigta." << endl;
    return 0;
}
