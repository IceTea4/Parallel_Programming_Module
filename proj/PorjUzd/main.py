import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from joblib import Parallel, delayed
import time

rng = np.random.default_rng(7)

n = 100
m = 40

# Esamų parduotuvių koordinatės intervale [-10,10]
existing_xy = rng.uniform(-10.0, 10.0, size=(n, 2))

# Pradinės naujų parduotuvių vietos
x0_new = rng.uniform(-10.0, 10.0, size=(m, 2))

# Porinė kaina tarp dviejų parduotuvių p=(x,y), q=(x,y): exp(-0.3*||p-q||^2)
def Cost_pair(p, q):
    d2 = np.sum((p - q) ** 2)
    return np.exp(-0.3 * d2)

# Vietos (statybos) kaina vienai parduotuvei p=(x,y)
def Cost_place(p):
    x, y = p
    return (x**4 + y**4) / 1000.0 + (np.sin(x) + np.cos(y)) / 5.0 + 0.4

# Bendra tikslo funkcija F
def objective(flat_new, existing):
    P = flat_new.reshape(-1, 2)

    # Vietos kainų suma (tik naujoms parduotuvėms)
    F = np.sum([Cost_place(p) for p in P])

    # Porinės kainos tarp naujų ir esamų
    for p in P:
        F += np.sum([Cost_pair(p, q) for q in existing])

    # Porinės kainos tarp pačių naujų (kiekvieną porą skaičiuojame 1 kartą: j<k)
    for j in range(len(P)):
        for k in range(j + 1, len(P)):
            F += Cost_pair(P[j], P[k])

    return float(F)

# Nuosekli gradiento versija (kryptis, kur F dideja)
def gradient_seq(flat_new, existing):
    P = flat_new.reshape(-1, 2)
    m_pts = len(P)
    grad = np.zeros_like(P)

    # Vietos kainos Cost_place išvestinės (norim zinot kuria kryptim mazeja greiciausiai F)
    grad[:, 0] += 4.0 * P[:, 0] ** 3 / 1000.0 + np.cos(P[:, 0]) / 5.0
    grad[:, 1] += 4.0 * P[:, 1] ** 3 / 1000.0 - np.sin(P[:, 1]) / 5.0

    # Porinės kainos su esamomis parduotuvėmis
    for j in range(m_pts):
        p = P[j]
        diffs = p - existing
        d2 = np.sum(diffs ** 2, axis=1)
        e = np.exp(-0.3 * d2)
        grad[j] += np.sum(((-0.6) * e)[:, None] * diffs, axis=0)

    # Porinės kainos tarp pačių naujų: j<k
    for j in range(m_pts):
        for k in range(j + 1, m_pts):
            diff = P[j] - P[k]
            d2 = np.dot(diff, diff)
            e = np.exp(-0.3 * d2)
            gpair = (-0.6) * e * diff
            grad[j] += gpair
            grad[k] -= gpair

    return grad.reshape(-1)

# Lygiagretus gradientas
def gradient_parallel(flat_new, existing, n_jobs=1):
    # Jei prašoma tik 1 gija – naudojam paprastą nuoseklią versiją
    if n_jobs == 1:
        return gradient_seq(flat_new, existing)

    P = flat_new.reshape(-1, 2)
    m_pts = len(P)

    #kiekvienai parduotuvei atskirai skaiciuoja gradienta
    def grad_for_j(j):
        p_j = P[j]

        # Vietos kainos Cost_place išvestinės
        gx = 4.0 * p_j[0] ** 3 / 1000.0 + np.cos(p_j[0]) / 5.0
        gy = 4.0 * p_j[1] ** 3 / 1000.0 - np.sin(p_j[1]) / 5.0
        g = np.array([gx, gy], dtype=float)

        # Porinės kainos su esamomis parduotuvėmis
        diffs_e = p_j - existing
        d2_e = np.sum(diffs_e ** 2, axis=1)
        e_e = np.exp(-0.3 * d2_e)
        g += np.sum(((-0.6) * e_e)[:, None] * diffs_e, axis=0)

        # Porinės kainos su kitomis naujomis parduotuvėmis
        diffs_n = p_j - P
        d2_n = np.sum(diffs_n ** 2, axis=1)
        e_n = np.exp(-0.3 * d2_n)
        g += np.sum(((-0.6) * e_n)[:, None] * diffs_n, axis=0)

        return g

    grads = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(grad_for_j)(j) for j in range(m_pts)
    )

    grad_arr = np.vstack(grads)
    return grad_arr.reshape(-1)

# Naudojama tik patikrai, ne optimizacijai
# letesnis, beveik visada teisingas, naudojamas tik gradiento tikrinimui
# koordinate pakeicia eps ir vel skaiciuoja F
def numeric_grad(flat_new, existing, eps=1e-6):
    g = np.zeros_like(flat_new)
    f0 = objective(flat_new, existing)
    for i in range(len(flat_new)):
        x_pert = flat_new.copy()
        x_pert[i] += eps
        g[i] = (objective(x_pert, existing) - f0) / eps
    return g

# Gradientinis metodas
def gradient_method(existing, x0, max_iter=2000, tol=1e-6,
                    step=0.01, track_every=1, n_jobs=1):
    x = x0.reshape(-1).astype(float)
    m = x.size // 2

    # Trajektorijos kaupimas: kiekvienai naujai parduotuvei saugom visi priimti taškai
    paths = [[x[2 * j:2 * j + 2].copy()] for j in range(m)]
    hist = []

    f = objective(x, existing)

    for it in range(1, max_iter + 1):
        g = gradient_parallel(x, existing, n_jobs=n_jobs)
        gnorm = float(np.linalg.norm(g))

        # Sustabdymas pagal mažą gradiento normą
        if gnorm < tol:
            hist.append({"iter": it, "f": f, "step": 0.0,
                         "gnorm": gnorm, "stop": "||grad||<tol"})
            break

        # Vienas gradientinio metodo žingsnis su fiksuotu žingsniu 'step'
        x_new = x - step * g
        f_new = objective(x_new, existing)

        # Paprasta apsauga: jei F padidėjo labai ryškiai, stabdom (nenorim „iššokti“)
        if f_new > f and f_new - f > 1e-6:
            hist.append({"iter": it, "f": f, "step": step,
                         "gnorm": gnorm, "stop": "F padidėjo"})
            break

        # Patvirtiname žingsnį
        x = x_new
        f = f_new

        # Užfiksuojame trajektorijų taškus ir istoriją
        if it % track_every == 0:
            for j in range(m):
                paths[j].append(x[2 * j:2 * j + 2].copy())
            hist.append({"iter": it, "f": f, "step": step, "gnorm": gnorm})

    else:
        # pasiekta max_iter
        hist.append({"iter": max_iter, "f": f, "step": step,
                     "gnorm": float(np.linalg.norm(
                         gradient_parallel(x, existing, n_jobs=n_jobs)
                     )),
                     "stop": "max_iter"})

    return x, hist, paths

def run_experiment_for_dataset(n, m, max_iter, step, n_jobs, repeats=3):
    """
    Sugeneruoja duomenų rinkinį su n esamų ir m naujų parduotuvių,
    paleidžia gradientinį metodą 'repeats' kartus ir grąžina vidutinį laiką.
    """
    rng = np.random.default_rng(7)

    existing_xy = rng.uniform(-10.0, 10.0, size=(n, 2))
    x0_new = rng.uniform(-10.0, 10.0, size=(m, 2))

    times = []
    for r in range(repeats):
        x0 = x0_new.copy()
        start = time.perf_counter()
        x_opt, history, paths = gradient_method(
            existing=existing_xy,
            x0=x0,
            max_iter=max_iter,
            tol=1e-6,
            step=step,
            track_every=10,
            n_jobs=n_jobs
        )
        end = time.perf_counter()
        times.append(end - start)

    avg_time = sum(times) / len(times)
    return avg_time

if __name__ == "__main__":
    max_iter = 1500
    step = 0.01

    # 8 skirtingos apimties duomenų rinkiniai
    # datasets = [
    #     ("S1", 6, 3),
    #     ("S2", 20, 10),
    #     ("S3", 50, 20),
    #     ("S4", 100, 30),
    #     ("S5", 100, 40),
    #     ("S6", 100, 50),
    #     ("S7", 200, 60),
    #     ("S8", 200, 70),
    # ]

    datasets = [
        ("S5", 100, 40),
    ]

    JOBS = [1, 4]

    print("=== Vykdymo laiko matavimai skirtingiems duomenų rinkiniams ir n_jobs ===")

    results = []

    # for name, n_i, m_i in datasets:
    #     print(f"\n--- Rinkinys {name}: n={n_i}, m={m_i} ---")
    #     for jobs in JOBS:
    #         avg_t = run_experiment_for_dataset(
    #             n=n_i,
    #             m=m_i,
    #             max_iter=max_iter,
    #             step=step,
    #             n_jobs=jobs,
    #             repeats=1
    #         )
    #         print(f"n_jobs = {jobs:2d} -> vidutinis laikas ~ {avg_t:.3f} s")
    #
    #         results.append({
    #             "dataset": name,
    #             "n": n_i,
    #             "m": m_i,
    #             "n_jobs": jobs,
    #             "avg_time": avg_t,
    #         })

    # results_df = pd.DataFrame(results)

    # print("\n=== Optimalus n_jobs kiekvienam duomenų rinkiniui ===")
    # for name, n_i, m_i in datasets:
    #     sub = results_df[results_df["dataset"] == name]
    #     best_row = sub.loc[sub["avg_time"].idxmin()]
    #     best_jobs = int(best_row["n_jobs"])
    #     best_time = float(best_row["avg_time"])
    #     print(f"{name}: n={n_i}, m={m_i} -> geriausia n_jobs = {best_jobs}, laikas ~ {best_time:.3f} s")
    #
    # for name, n_i, m_i in datasets:
    #     sub = results_df[results_df["dataset"] == name].sort_values("n_jobs")
    #
    #     plt.figure(figsize=(6, 4))
    #     plt.plot(sub["n_jobs"], sub["avg_time"], marker="o")
    #     plt.xlabel("n_jobs (gijų skaičius)")
    #     plt.ylabel("Vidutinis vykdymo laikas, s")
    #     plt.title(f"Rinkinys {name}: n={n_i}, m={m_i}")
    #     plt.grid(True)
    #     plt.xticks(JOBS)
    #     plt.show()

    # Pradinis taškas naujoms parduotuvėms
    x0 = x0_new.copy()
    x0_flat = x0.reshape(-1)

    jobs = 1

    print("=== Gradiento tikrinimas pradiniame taške x0 ===")
    g_seq = gradient_seq(x0_flat, existing_xy)
    g_par = gradient_parallel(x0_flat, existing_xy, n_jobs=jobs)
    g_num = numeric_grad(x0_flat, existing_xy, eps=1e-6)

    print(f"||g_seq||_2  = {np.linalg.norm(g_seq):.6e}")
    print(f"||g_par||_2  = {np.linalg.norm(g_par):.6e}")
    print(f"||g_num||_2  = {np.linalg.norm(g_num):.6e}")
    print(f"max|g_seq - g_par|  = {np.max(np.abs(g_seq - g_par)):.6e}")
    print(f"max|g_seq - g_num|  = {np.max(np.abs(g_seq - g_num)):.6e}")
    print(f"max|g_par - g_num|  = {np.max(np.abs(g_par - g_num)):.6e}")
    print("Jei šie maksimalūs skirtumai yra maži (pvz. < 1e-5), gradientas įgyvendintas teisingai.\n")

    x_opt, history, paths = gradient_method(
        existing=existing_xy,
        x0=x0,
        max_iter=max_iter,
        tol=1e-6,
        step=step,
        track_every=1,
        n_jobs=jobs
    )

    P0 = x0.reshape(-1, 2)
    Popt = x_opt.reshape(-1, 2)

    iters = history[-1]["iter"]
    stop_reason = history[-1].get("stop", "finished")
    F0 = objective(P0.reshape(-1), existing_xy)
    Fopt = objective(x_opt, existing_xy)

    print("=== Gradientinis metodas (fiksuotas žingsnis, lygiagretus gradientas su joblib) ===")
    print("""
Tikslo funkcija F:

- naujų parduotuvių vietos (statybos) kaina:
    Cost_place(p) = (x^4 + y^4)/1000 + (sin(x) + cos(y))/5 + 0.4

- porinė kaina tarp dviejų parduotuvių p, q:
    Cost_pair(p,q) = exp( -0.3 * ||p - q||^2 )

Bendra funkcija:

    F = sum_{k=1..m} Cost_place(p_k)
        + sum_{k=1..m} sum_{i=1..n} Cost_pair(p_k, q_i)
        + sum_{1 <= j < k <= m} Cost_pair(p_j, p_k)

kur:
    q_i – esamos parduotuvės,
    p_k – naujų parduotuvių koordinatės.
""")
    print(f"n (esamos) = {n}, m (naujos) = {m}")
    print(f"Parametrai: step={history[-1].get('step', 0.01)}, tol=1e-6, max_iter={max_iter}, n_jobs={jobs}")
    print(f"Iteracijų sk.: {iters}")
    print(f"Sustabdymo priežastis: {stop_reason}")
    print(f"F: pradžia={F0:.6f}, pabaiga={Fopt:.6f} (pagerėjimas {F0 - Fopt:.6f})")

    df_existing = pd.DataFrame(existing_xy, columns=["x", "y"])
    df_start = pd.DataFrame(P0, columns=["x", "y"])
    df_final = pd.DataFrame(Popt, columns=["x", "y"])

    print("\n=== Esamos parduotuvės (x, y) ===")
    print(df_existing.to_string(index=False))
    print("\n=== Pradinės naujų (x, y) ===")
    print(df_start.to_string(index=False))
    print("\n=== Optimizuotos naujų (x, y) ===")
    print(df_final.to_string(index=False))

    input("\nPaspausk Enter, kad sugeneruotum grafikus...")

    plt.figure(figsize=(8, 8), dpi=140)

    plt.axhline(-10, color='black', linestyle=':', linewidth=0.8)
    plt.axhline(10,  color='black', linestyle=':', linewidth=0.8)
    plt.axvline(-10, color='black', linestyle=':', linewidth=0.8)
    plt.axvline(10,  color='black', linestyle=':', linewidth=0.8)
    plt.text(-9.8, 10.2, "City [-10,10]", fontsize=9)

    plt.scatter(existing_xy[:, 0], existing_xy[:, 1], marker='o', label='Esamos')

    plt.scatter(P0[:, 0],   P0[:, 1],   marker='^', label='Pradžios (naujos)')
    plt.scatter(Popt[:, 0], Popt[:, 1], marker='s', label='Optimizuotos (naujos)')

    step_mark_every = 1
    for path in paths:
        path = np.array(path)
        plt.plot(path[:, 0], path[:, 1], color='black', linewidth=1.0, alpha=0.7)
        plt.scatter(path[::step_mark_every, 0],
                    path[::step_mark_every, 1],
                    s=8, marker='o', color='black', alpha=0.9)

    plt.xlabel("x")
    plt.ylabel("y")
    plt.title("Parduotuvių išsidėstymas: pradinės, trajektorijos, galutinės")
    plt.legend(loc='best')
    plt.grid(True)
    plt.axis('equal')
    plt.show()

    its = [h["iter"] for h in history if "f" in h]
    vals = [h["f"] for h in history if "f" in h]
    plt.figure(figsize=(9, 4), dpi=140)
    plt.plot(its, vals, linewidth=1.5)
    plt.xlabel("Iteracija")
    plt.ylabel("Tikslo funkcija F")
    plt.title("F reikšmė per iteracijas (gradientinis metodas)")
    plt.grid(True)
    plt.show()

    xmin, xmax, ymin, ymax = -12, 12, -12, 12
    gx = np.linspace(xmin, xmax, 80)
    gy = np.linspace(ymin, ymax, 80)
    GX, GY = np.meshgrid(gx, gy)

    E = existing_xy
    Ex = E[:, 0][:, None, None]
    Ey = E[:, 1][:, None, None]

    d2 = (Ex - GX) ** 2 + (Ey - GY) ** 2

    heat = np.sum(np.exp(-0.3 * d2), axis=0)

    plt.figure(figsize=(7, 6), dpi=140)
    cs = plt.contourf(GX, GY, heat, levels=15)
    plt.colorbar(cs)
    plt.scatter(existing_xy[:, 0], existing_xy[:, 1], marker='o', label='Esamos')
    plt.scatter(Popt[:, 0], Popt[:, 1], marker='s', label='Optimizuotos')
    plt.title("Porinės kainos laukas esamų atžvilgiu (mažesnė – geriau)")
    plt.xlabel("x")
    plt.ylabel("y")
    plt.legend(loc='best')
    plt.axis('equal')
    plt.show()
