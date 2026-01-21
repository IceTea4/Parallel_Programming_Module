import hashlib
import multiprocessing as mp
import os
import socket
import time

HOST = "127.0.0.1"
PORT_IN = 5000   # C++ -> Python (užduotys)
PORT_OUT = 5001  # Python -> C++ (rezultatai)

# Protocol markers
MSG_BEGIN = "BEGIN"
MSG_END = "END"
MSG_RESULTS = "RESULTS"
MSG_DONE = "DONE"

# =====================================================
# TCP helperiai (line-based)
# -----------------------------------------------------
# TCP yra "stream", todėl kad turėtume aiškias žinutes,
# siunčiam "viena eilutė = vienas pranešimas" su '\n'
# =====================================================
def recv_line(conn: socket.socket) -> str:
    data = bytearray()
    while True:
        b = conn.recv(1)
        if not b:
            raise ConnectionError("Socket closed")
        data += b
        if b == b"\n":
            return data.decode("utf-8")

def send_line(conn: socket.socket, line: str) -> None:
    if not line.endswith("\n"):
        line += "\n"
    conn.sendall(line.encode("utf-8"))

# =====================================================
# "Sunki" CPU funkcija
# -----------------------------------------------------
# Payload: "games,winning"
# Rounds: kiek kartų kartoti SHA-256 (didina darbo trukmę)
# =====================================================
def cpu_heavy_py(payload: str, rounds: int) -> int:
    h = payload.encode("utf-8")
    for _ in range(rounds):
        h = hashlib.sha256(h).digest()
    return int.from_bytes(h[:4], "little", signed=False)

# =====================================================
# Worker procesas
# -----------------------------------------------------
# Ima užduotis iš q_in:
#    (idx, payload)
# Paskaičiuoja:
#    val = cpu_heavy_py(payload)
# Ir padeda į q_out:
#    (idx, val)
#
# Stabdymas:
#   - kai gauna None
#   - arba stop_event yra set()
# =====================================================
def worker_loop(q_in: mp.Queue, q_out: mp.Queue, rounds: int, stop_event) -> None:
    while not stop_event.is_set():
        item = q_in.get()
        if item is None:
            break
        idx, payload = item
        val = cpu_heavy_py(payload, rounds)
        q_out.put((idx, val))

# =====================================================
# Receiver procesas (priima tasks iš C++)
# -----------------------------------------------------
# 1) listen PORT_IN
# 2) accept
# 3) perskaito "BEGIN n"
# 4) meta_q.put(n) -> praneša sender procesui kiek bus rezultatų
# 5) skaito n eilučių: "idx;payload" -> q_in.put(...)
# 6) skaito "END"
# 7) į q_in įdeda None worker'iams
# =====================================================
def receiver_process(q_in: mp.Queue, meta_q: mp.Queue, worker_count: int, stop_event) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT_IN))
    srv.listen(1)
    print(f"[PY][RECV] Listening {HOST}:{PORT_IN}")

    try:
        conn, addr = srv.accept()
        with conn:
            print(f"[PY][RECV] Connected from {addr}")

            # BEGIN n
            header = recv_line(conn).strip()
            parts = header.split()
            if len(parts) != 2 or parts[0] != MSG_BEGIN:
                raise ValueError(f"Bad header: {header!r} (expected 'BEGIN n')")
            n = int(parts[1])

            # informuojam sender'į, kiek rezultatų bus
            meta_q.put(n)

            # tasks (stream)
            for _ in range(n):
                line = recv_line(conn).strip()
                idx_s, payload = line.split(";", 1)
                q_in.put((int(idx_s), payload))

            # END
            end = recv_line(conn).strip()
            if end != MSG_END:
                raise ValueError(f"Bad end marker: {end!r} (expected 'END')")

    except Exception:
        # jei kažkas blogai — stabdom viską
        stop_event.set()
        raise

    finally:
        # VISADA duodam worker'iams pabaigos signalus
        for _ in range(worker_count):
            q_in.put(None)
        srv.close()
        print("[PY][RECV] Receiver exiting.")

# =====================================================
# Sender procesas (stream’ina rezultatus į C++)
# -----------------------------------------------------
# 1) listen PORT_OUT
# 2) accept
# 3) n = meta_q.get()  (palaukia kol receiver pasakys n)
# 4) siunčia "RESULTS n"
# 5) stream’ina (idx,val) iš q_out kaip "idx;val"
# 6) kai išsiunčia n -> siunčia "DONE"
# =====================================================
def sender_process(q_out: mp.Queue, meta_q: mp.Queue, stop_event) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT_OUT))
    srv.listen(1)
    print(f"[PY][SEND] Listening {HOST}:{PORT_OUT}")

    try:
        conn, addr = srv.accept()
        with conn:
            print(f"[PY][SEND] Connected from {addr}")

            # laukiam "n" iš receiver proceso
            n = meta_q.get()

            # iškart pasakom C++ kiek bus rezultatų
            send_line(conn, f"{MSG_RESULTS} {n}")

            # streaminam rezultatus, kai tik atsiranda q_out
            sent = 0
            while sent < n:
                if stop_event.is_set():
                    break
                idx, val = q_out.get()
                send_line(conn, f"{idx};{val}")
                sent += 1

            if sent == n and not stop_event.is_set():
                send_line(conn, MSG_DONE)

            print(f"[PY][SEND] Sent {sent}/{n} results.")

    except (BrokenPipeError, ConnectionError, OSError):
        stop_event.set()

    finally:
        srv.close()
        print("[PY][SEND] Sender exiting.")

# =====================================================
# MAIN
# -----------------------------------------------------
# 1) paleidžia worker procesus (CPU parallel)
# 2) paleidžia receiver procesą (PORT_IN)
# 3) paleidžia sender procesą (PORT_OUT)
# =====================================================
def main() -> None:
    cpu = os.cpu_count() or 4

    # paliekam 1 branduolį C++ daliai
    default_workers = max(1, cpu - 1)

    worker_count = int(os.environ.get("PY_WORKERS", str(default_workers)))
    rounds = int(os.environ.get("PY_ROUNDS", "60000"))

    q_in: mp.Queue = mp.Queue()
    q_out: mp.Queue = mp.Queue()

    # meta_q naudojam tik vienam dalykui:
    # perduoti "n" (kiek rezultatų bus) iš receiver -> sender
    meta_q: mp.Queue = mp.Queue()

    stop_event = mp.Event()

    # 1) workers (vieną kartą)
    workers = []
    for _ in range(worker_count):
        p = mp.Process(target=worker_loop, args=(q_in, q_out, rounds, stop_event), daemon=True)
        p.start()
        workers.append(p)

    # 2) receiver + sender (atskirai)
    p_recv = mp.Process(target=receiver_process, args=(q_in, meta_q, worker_count, stop_event), daemon=True)
    p_send = mp.Process(target=sender_process, args=(q_out, meta_q, stop_event), daemon=True)

    t0 = time.perf_counter()
    p_recv.start()
    p_send.start()

    # laukiam kol baigs
    p_recv.join()
    p_send.join()

    stop_event.set()

    # sujoininam workers
    for p in workers:
        p.join(timeout=2)

    t1 = time.perf_counter()
    print(f"[PY] Server done workers={worker_count} | rounds={rounds}")

if __name__ == "__main__":
    # nusako kaip kuriami nauji procesai
    # paleidžia visiškai naują Python interpretatorių
    mp.set_start_method("spawn")
    main()
