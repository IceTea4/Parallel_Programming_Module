__kernel void f_cl(__global const int* games,
                   __global const float* winning,
                   __global uint* out,
                   const uint n,
                   const uint rounds) {

    uint gid = get_global_id(0);
    uint gsz = get_global_size(0);

    for (uint i = gid; i < n; i += gsz) {
        uint w = (uint)(winning[i] * 10.0f); // pvz 50.3 -> 503
        uint x = ((uint)games[i]) * 2654435761u ^ (w * 1597334677u) ^ 12345u;

        for (uint k = 0; k < rounds; k++) {
            x = (x ^ (x << 13)) * 1103515245u + 12345u;
            x = x ^ (x >> 7);
        }
        out[i] = x;
    }
}
