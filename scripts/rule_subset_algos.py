#!/usr/bin/env python3
"""Subset-selection algorithms for post-hoc distilled-rule pruning.

Every selection algorithm `rule_subset_search.py search --search-algo` can run
lives in this file, in one place, ordered from the classical baseline to the
contemporary methods:

  0. shared kernel      ratio objective, its gradient, linear surrogates
  1. greedy             forward selection (the original baseline)
  2. lazy               CELF-style lazy forward selection (accelerator)
  3. polish             backward elimination (used as a post-pass by others)
  4. localsearch        add / drop / swap to a local optimum   (Feige,
                        Mirrokni & Vondrak 2011 style non-monotone local search)
  5. distorted          distorted greedy for  max g(S) - c(S)  (Harshaw,
                        Feldman, Ward & Karbasi, ICML 2019)
  6. dinkelbach         fractional programming on the F1 ratio, with any of
                        the above as the inner linear solver (Dinkelbach 1967)
  7. poss               Pareto Optimization for Subset Selection
                        (Qian, Yu & Zhou, NeurIPS 2015)
  8. porss              POSS + recombination (Qian et al., 2022)

WHY ANYTHING BUT GREEDY.  The objective is pooled F1, a *ratio*:

    F1 = 2*P*R/(P+R),  P = A/B,  R = C/D
    A = tp      B = tp + fp       (extracted count)
    C = tp_recall                 D = tp_recall + fn   (gold count, constant)

so F1 = 2AC / (A*D + C*B).  A and C are coverage-like and roughly monotone
submodular in the rule set (a rule's marginal true positives shrink as other
rules already cover those gold spans); B is roughly modular (spurious spans
mostly add up independently).  That makes this a submodular-coverage /
modular-cost ratio problem.  Stepping greedily *on F1 itself* is myopic and,
once the objective goes non-monotone (which it does as soon as FP dominates),
plain forward selection has no approximation guarantee at all.  The methods
below either optimise the right linearisation of the ratio (5, 6), escape the
local optima forward-then-backward cannot (4), or search the whole
size-vs-score frontier at once (7, 8).

INTERFACE.  Each algorithm takes the `Search` object from rule_subset_search
(the in-memory replay + exact scorer), an options dict, and a log callable,
and returns a Result:

    selected   list of unit ids (the answer)
    curve      list of dicts, one per step, for the CSV
    ladder     optional [(k, frozenset(units))] nested-by-size candidate
               solutions, ascending k.  The CV driver scores every rung on
               held-out folds to pick a stopping size honestly.  None means
               the algorithm produces a single set with no size ladder.
    info       free-form dict recorded in selection.json

It uses only the public surface of Search: papers, paper_set, obj,
candidate_units(), evaluate(), rescore(), pooled_counts(), pooled_f1(), row().
Nothing here imports rule_subset_search, so there is no import cycle.
"""
import heapq
import random
from collections import OrderedDict, namedtuple

Result = namedtuple("Result", "selected curve ladder info")

EPS = 1e-9


# ---------------------------------------------------------------------------
# 0. shared kernel: the ratio objective, its gradient, linear surrogates
# ---------------------------------------------------------------------------

def counts_to_f1(agg):
    """Pooled F1 from a {tp, tp_recall, fp, fn} aggregate.

    Identical to rule_subset_search.prf()[2]; duplicated here so the algorithms
    module stays import-free."""
    b = agg["tp"] + agg["fp"]
    d = agg["tp_recall"] + agg["fn"]
    p = agg["tp"] / b if b else 0.0
    r = agg["tp_recall"] / d if d else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def ratio_gradient(agg):
    """(w_A, w_B, w_C) = dF1/d(tp, extracted, tp_recall) at this count vector.

    The linear surrogate  h(S) = w_A*A(S) + w_B*B(S) + w_C*C(S)  is the
    first-order model of F1 around the current solution.  Maximising h and
    re-linearising is exactly Dinkelbach's method for fractional programming:
    in m1 mode (where tp == tp_recall and F1 collapses to 2tp/(|gold|+|ext|))
    this reduces algebraically to the textbook update
    `maximise tp - theta/(2-theta) * fp`.  In m3 mode tp and tp_recall differ,
    F1 is no longer a ratio of two linear count functions, and the gradient
    form is the correct generalisation.

    Weights are scaled so |w_A| + |w_C| == 1; scaling never moves an argmax,
    it only keeps the distorted-greedy bookkeeping numerically comparable
    across iterations."""
    a = float(agg["tp"])
    b = float(agg["tp"] + agg["fp"])
    c = float(agg["tp_recall"])
    d = float(agg["tp_recall"] + agg["fn"])
    m = a * d + c * b
    if m <= 0:
        # no extractions and/or no gold: bootstrap by chasing raw coverage
        return 1.0, 0.0, 1.0
    n = 2.0 * a * c
    w_a = (2.0 * c * m - n * d) / (m * m)
    w_b = (-n * c) / (m * m)
    w_c = (2.0 * a * m - n * b) / (m * m)
    s = abs(w_a) + abs(w_c)
    if s > EPS:
        w_a, w_b, w_c = w_a / s, w_b / s, w_c / s
    return w_a, w_b, w_c


def surrogate_value(agg, w):
    """h(S) for the linearised ratio."""
    w_a, w_b, w_c = w
    return (w_a * agg["tp"]
            + w_b * (agg["tp"] + agg["fp"])
            + w_c * agg["tp_recall"])


def gc_split(w):
    """Split the surrogate into (g, c) with g monotone non-negative, c >= 0.

    Distorted greedy is stated for  max g(S) - c(S)  with g monotone
    submodular non-negative and c modular non-negative.  Splitting by the sign
    of each weight is exact -- g(S) - c(S) == h(S) for every S -- and puts the
    monotone-increasing count terms (tp, extracted, tp_recall all only grow as
    rules are added) on the g side whenever their weight is positive.

    Caveat kept honest: c is only *approximately* modular here, because
    cross-rule dedup in _merge_objects makes the extracted count subadditive.
    Values are always measured exactly against the replay, so only the theory's
    precondition is approximate, never the reported numbers."""
    w_a, w_b, w_c = w
    pos = lambda x: max(x, 0.0)      # noqa: E731
    neg = lambda x: max(-x, 0.0)     # noqa: E731

    def g_val(agg):
        return (pos(w_a) * agg["tp"]
                + pos(w_b) * (agg["tp"] + agg["fp"])
                + pos(w_c) * agg["tp_recall"])

    def c_val(agg):
        return (neg(w_a) * agg["tp"]
                + neg(w_b) * (agg["tp"] + agg["fp"])
                + neg(w_c) * agg["tp_recall"])

    return g_val, c_val


def _f1_scorer(search):
    """counts -> true pooled F1 in the search's objective mode."""
    return counts_to_f1


def _prefix_ladder(path):
    """Nested-by-size candidate solutions from an ordered selection path."""
    out, acc = [(0, frozenset())], set()
    for i, u in enumerate(path, 1):
        acc.add(u)
        out.append((i, frozenset(acc)))
    return out


def _best_prefix(search, path, log=None, tag=""):
    """Best prefix of an ordered path by TRUE pooled F1.

    Algorithms that optimise a surrogate (distorted, dinkelbach) must be judged
    on the real objective before returning."""
    active, pp = set(), search.evaluate(set())
    best = (search.pooled_f1(pp), 0)
    for i, u in enumerate(path, 1):
        active.add(u)
        pp = search.rescore(pp, active, [u])
        f1 = search.pooled_f1(pp)
        if f1 > best[0] + EPS:
            best = (f1, i)
    if log and tag:
        log(f"  [{tag}] best prefix k={best[1]} true F1={best[0]:.4f}")
    return list(path[:best[1]]), best[0]


# ---------------------------------------------------------------------------
# 1. greedy forward selection  (the original baseline)
# ---------------------------------------------------------------------------

def _greedy_core(search, score_fn, patience, log, tag, pool=None,
                 active=None, per_paper=None, record=True):
    """Shared forward-selection loop.

    score_fn maps a pooled count aggregate to the scalar being maximised, so
    the same loop drives selection on true F1 (greedy) and on a linear
    surrogate (dinkelbach's inner solve).  Candidates are evaluated
    incrementally: only the papers a unit actually fires on are re-replayed.

    Ties are broken by unit id, and since the pool is id-sorted and we replace
    only on strict improvement, the winner is the lowest id among ties -- the
    same order the original sort-by-(-f1, uid) produced."""
    active = set() if active is None else set(active)
    pp = search.evaluate(active) if per_paper is None else dict(per_paper)
    pool = list(search.candidate_units()) if pool is None else list(pool)
    pool = [u for u in pool if u not in active]
    cur = score_fn(search.pooled_counts(pp))
    best_score, since_best, best_at = cur, 0, 0
    path, curve = [], ([search.row(0, None, pp)] if record else [])
    log(f"  [{tag}] start score={cur:.4f}, pool={len(pool)} units")
    step = 0
    while pool and since_best < patience:
        step += 1
        top = None
        for u in pool:
            trial = search.rescore(pp, active | {u}, (u,))
            sc = score_fn(search.pooled_counts(trial))
            if top is None or sc > top[0] + EPS:
                top = (sc, u, trial)
        sc, u, trial = top
        active.add(u)
        path.append(u)
        pool.remove(u)
        pp = trial
        if record:
            curve.append(search.row(step, u, pp))
        marker = ""
        if sc > best_score + EPS:
            best_score, since_best, best_at = sc, 0, step
            marker = " *"
        else:
            since_best += 1
        if step % 10 == 0 or marker:
            log(f"  [{tag}] step {step}: +{u} -> {sc:.4f}{marker}")
    log(f"  [{tag}] stopped after {step} steps; best {best_score:.4f} "
        f"at k={best_at}")
    return path, best_at, best_score, curve


def greedy(search, opts, log=print):
    """Classical forward selection on pooled F1 -- unchanged baseline."""
    patience = opts.get("patience", 25)
    path, best_at, best_f1, curve = _greedy_core(
        search, counts_to_f1, patience, log, "greedy")
    return Result(list(path[:best_at]), curve, _prefix_ladder(path),
                  {"steps_taken": len(path), "best_at": best_at,
                   "train_score": best_f1})


# ---------------------------------------------------------------------------
# 2. lazy greedy / CELF  (accelerator, same intent as greedy)
# ---------------------------------------------------------------------------

def lazy(search, opts, log=print):
    """CELF lazy forward selection (Minoux 1978; Leskovec et al. 2007).

    Keeps stale marginal gains in a max-heap and only re-evaluates the top
    candidate, which cuts the O(n) full sweep per step down to a handful of
    re-evaluations.  Under true submodularity this returns exactly the greedy
    answer; pooled F1 is only approximately submodular, so a gain can grow
    between steps and the guarantee is heuristic.  Termination is forced by
    accepting any candidate re-evaluated twice within the same step, so a gain
    that keeps rising cannot spin the inner loop."""
    patience = opts.get("patience", 25)
    active = set()
    pp = search.evaluate(active)
    cur = search.pooled_f1(pp)
    pool = list(search.candidate_units())
    heap = []
    for u in pool:
        trial = search.rescore(pp, {u}, (u,))
        heapq.heappush(heap, (-(search.pooled_f1(trial) - cur), u))
    log(f"  [lazy] start F1({search.obj})={cur:.4f}, pool={len(pool)} units")
    path, curve = [], [search.row(0, None, pp)]
    best_f1, since_best, best_at = cur, 0, 0
    step, evals = 0, len(pool)
    while heap and since_best < patience:
        step += 1
        seen = set()
        while True:
            _stale, u = heapq.heappop(heap)
            trial = search.rescore(pp, active | {u}, (u,))
            evals += 1
            gain = search.pooled_f1(trial) - cur
            # accept if still the best bound, if the heap is empty, or if we
            # have already re-checked this unit this step (anti-spin guard)
            if not heap or -gain <= heap[0][0] + EPS or u in seen:
                break
            seen.add(u)
            heapq.heappush(heap, (-gain, u))
        active.add(u)
        path.append(u)
        pp = trial
        cur = cur + gain
        curve.append(search.row(step, u, pp))
        marker = ""
        if cur > best_f1 + EPS:
            best_f1, since_best, best_at = cur, 0, step
            marker = " *"
        else:
            since_best += 1
        if step % 10 == 0 or marker:
            log(f"  [lazy] step {step}: +{u} -> {cur:.4f}{marker}")
    log(f"  [lazy] stopped after {step} steps; best {best_f1:.4f} at "
        f"k={best_at}; {evals} evaluations "
        f"(full greedy would need ~{step * len(pool)})")
    return Result(list(path[:best_at]), curve, _prefix_ladder(path),
                  {"steps_taken": len(path), "best_at": best_at,
                   "evaluations": evals, "train_score": best_f1})


# ---------------------------------------------------------------------------
# 3. backward elimination polish  (post-pass, shared by the others)
# ---------------------------------------------------------------------------

def polish(search, selected, log=print):
    """Drop any single unit whose removal raises pooled F1, to a fixed point."""
    active = set(selected)
    pp = search.evaluate(active)
    best = search.pooled_f1(pp)
    improved = True
    while improved:
        improved = False
        for u in sorted(active):
            trial = search.rescore(pp, active - {u}, (u,))
            f1 = search.pooled_f1(trial)
            if f1 > best + EPS:
                active.discard(u)
                pp, best = trial, f1
                improved = True
                log(f"  [polish] -{u} -> {best:.4f}")
    return sorted(active), best


# ---------------------------------------------------------------------------
# 4. local search: add / drop / swap  (non-monotone local search)
# ---------------------------------------------------------------------------

def localsearch(search, opts, log=print):
    """Add / drop / (1,1)-swap moves until no single move improves.

    Forward-then-backward (what greedy + polish does) cannot reach a solution
    that requires trading one selected rule for an unselected one, which is
    precisely the interaction case -- two rules whose spans suppress each other
    inside a group's extract function, or that dedup against each other in
    _merge_objects.  Adding swaps is the cheapest real escape from those local
    optima, and is the local-search scheme with a 1/3 guarantee for
    non-monotone submodular maximisation (Feige, Mirrokni & Vondrak 2011).

    Full swap enumeration is |S| x |pool| evaluations per round, so swaps are
    restricted to the `ls_swap_width` most promising drops crossed with the
    most promising adds -- both ranked by their exact single-move deltas, which
    this round has already computed anyway."""
    seed_mode = opts.get("ls_seed", "greedy")
    max_rounds = opts.get("ls_rounds", 30)
    width = opts.get("ls_swap_width", 20)
    patience = opts.get("patience", 25)

    if seed_mode == "greedy":
        path, best_at, _f1, _c = _greedy_core(
            search, counts_to_f1, patience, log, "ls-seed", record=False)
        active = set(path[:best_at])
    elif seed_mode == "full":
        active = set(search.candidate_units())
    else:
        active = set()

    pp = search.evaluate(active)
    cur = search.pooled_f1(pp)
    all_units = list(search.candidate_units())
    curve = [search.row(0, None, pp, note=f"seed:{seed_mode}")]
    log(f"  [localsearch] seed={seed_mode} |S|={len(active)} F1={cur:.4f}")

    n_add = n_drop = n_swap = 0
    for rnd in range(1, max_rounds + 1):
        outside = [u for u in all_units if u not in active]
        adds, drops = [], []
        for u in outside:
            trial = search.rescore(pp, active | {u}, (u,))
            adds.append((search.pooled_f1(trial) - cur, u, trial))
        for u in sorted(active):
            trial = search.rescore(pp, active - {u}, (u,))
            drops.append((search.pooled_f1(trial) - cur, u, trial))
        adds.sort(key=lambda x: (-x[0], x[1]))
        drops.sort(key=lambda x: (-x[0], x[1]))

        best_move = None                       # (delta, kind, payload, pp)
        if adds and adds[0][0] > EPS:
            best_move = (adds[0][0], "add", (adds[0][1],), adds[0][2])
        if drops and drops[0][0] > EPS and (
                best_move is None or drops[0][0] > best_move[0] + EPS):
            best_move = (drops[0][0], "drop", (drops[0][1],), drops[0][2])

        # swaps: top-width candidates on each side, evaluated exactly
        for _d_out, u_out, _t in drops[:width]:
            for _d_in, u_in, _t2 in adds[:width]:
                cand = (active - {u_out}) | {u_in}
                trial = search.rescore(pp, cand, (u_out, u_in))
                delta = search.pooled_f1(trial) - cur
                if best_move is None or delta > best_move[0] + EPS:
                    best_move = (delta, "swap", (u_out, u_in), trial)

        if best_move is None or best_move[0] <= EPS:
            log(f"  [localsearch] local optimum after {rnd - 1} move(s)")
            break
        delta, kind, payload, trial = best_move
        if kind == "add":
            active.add(payload[0]); n_add += 1
            note = f"+{payload[0]}"
        elif kind == "drop":
            active.discard(payload[0]); n_drop += 1
            note = f"-{payload[0]}"
        else:
            active.discard(payload[0]); active.add(payload[1]); n_swap += 1
            note = f"-{payload[0]} +{payload[1]}"
        pp, cur = trial, cur + delta
        curve.append(search.row(rnd, None, pp, note=note))
        log(f"  [localsearch] round {rnd}: {kind} {note} -> {cur:.4f} "
            f"(|S|={len(active)})")
    else:
        log(f"  [localsearch] hit ls_rounds={max_rounds} without converging")

    return Result(sorted(active), curve, None,
                  {"seed": seed_mode, "adds": n_add, "drops": n_drop,
                   "swaps": n_swap, "train_score": cur})


# ---------------------------------------------------------------------------
# 5. distorted greedy  (Harshaw, Feldman, Ward & Karbasi, ICML 2019)
# ---------------------------------------------------------------------------

def _distorted_core(search, w, k, log, tag="distorted"):
    """Distorted greedy for  max g(S) - c(S)  under the (g, c) split of w.

    At iteration i of k the marginal gain of g is discounted by
    (1 - 1/k)^(k-i-1) while the cost is charged in full, so an element must
    keep earning its cost as the horizon shortens.  This is what gives a
    guarantee where plain greedy has none once the objective is non-monotone.

    Two faithful details: an element that loses an iteration is NOT removed
    from the pool -- the distortion factor rises toward 1, so it can win later
    -- and an iteration that finds no positively-scoring element simply adds
    nothing rather than terminating."""
    g_val, c_val = gc_split(w)
    active, pp = set(), search.evaluate(set())
    path, curve = [], [search.row(0, None, pp, note="distorted:start")]
    k = max(1, int(k))
    for i in range(k):
        factor = (1.0 - 1.0 / k) ** (k - i - 1)
        base = search.pooled_counts(pp)
        base_g, base_c = g_val(base), c_val(base)
        top = None
        for u in search.candidate_units():
            if u in active:
                continue
            trial = search.rescore(pp, active | {u}, (u,))
            agg = search.pooled_counts(trial)
            score = factor * (g_val(agg) - base_g) - (c_val(agg) - base_c)
            if top is None or score > top[0] + EPS:
                top = (score, u, trial)
        if top is None:
            break
        score, u, trial = top
        if score > EPS:
            active.add(u)
            path.append(u)
            pp = trial
            curve.append(search.row(len(path), u, pp,
                                    note=f"iter{i} d={score:.4g}"))
        if (i + 1) % 10 == 0 or score > EPS:
            log(f"  [{tag}] iter {i + 1}/{k} factor={factor:.3f} "
                f"{'+' + u if score > EPS else 'skip'} "
                f"dist={score:+.4g} |S|={len(active)} "
                f"F1={search.pooled_f1(pp):.4f}")
    return path, curve


def distorted(search, opts, log=print):
    """One round of distorted greedy on the ratio's linearisation.

    The surrogate weights are taken at the FULL rule set -- the state the
    distillation run actually leaves behind and that this tool exists to prune
    -- so the linearisation is anchored at the operating point of interest.
    Sweeping the weights instead of fixing them once is what `dinkelbach`
    does."""
    all_units = set(search.candidate_units())
    anchor = opts.get("distorted_anchor", "full")
    pp0 = search.evaluate(all_units if anchor == "full" else set())
    w = ratio_gradient(search.pooled_counts(pp0))
    k = opts.get("distorted_k") or len(all_units)
    log(f"  [distorted] anchor={anchor} k={k} "
        f"w=(tp {w[0]:+.4f}, ext {w[1]:+.4f}, tp_recall {w[2]:+.4f})")
    path, curve = _distorted_core(search, w, k, log)
    sel, f1 = _best_prefix(search, path, log, "distorted")
    return Result(sel, curve, _prefix_ladder(path),
                  {"weights": list(w), "k": k, "anchor": anchor,
                   "path_len": len(path), "train_score": f1})


# ---------------------------------------------------------------------------
# 6. Dinkelbach fractional programming on the F1 ratio
# ---------------------------------------------------------------------------

def dinkelbach(search, opts, log=print):
    """Iterated linearisation of the F1 ratio (Dinkelbach 1967).

    Greedily stepping on F1 optimises the ratio myopically.  Instead: hold the
    current operating point fixed, maximise the LINEAR surrogate
    h(S) = w.counts(S) with w = dF1/dcounts there, move to the new solution,
    re-linearise, repeat.  Each inner problem is a clean
    submodular-gain-minus-modular-cost problem -- which is exactly what
    distorted greedy is for -- and the outer iteration converges in a handful
    of rounds.

    Every round's answer is scored on TRUE F1 (best prefix of its path) before
    it is accepted, so a surrogate that overshoots can never make the reported
    solution worse than the previous round's."""
    rounds = opts.get("dink_rounds", 6)
    inner = opts.get("dink_inner", "distorted")
    patience = opts.get("patience", 25)
    all_units = set(search.candidate_units())

    anchor_pp = search.evaluate(
        all_units if opts.get("dink_anchor", "full") == "full" else set())
    agg = search.pooled_counts(anchor_pp)
    best_sel, best_f1 = [], search.pooled_f1(search.evaluate(set()))
    best_path, curve, hist = [], [], []

    for it in range(1, rounds + 1):
        w = ratio_gradient(agg)
        log(f"  [dinkelbach] round {it}: theta={counts_to_f1(agg):.4f} "
            f"w=(tp {w[0]:+.4f}, ext {w[1]:+.4f}, tp_recall {w[2]:+.4f})")
        if inner == "distorted":
            k = opts.get("distorted_k") or len(all_units)
            path, sub = _distorted_core(search, w, k, log,
                                        tag=f"dink{it}")
        else:
            score_fn = (lambda a, _w=w: surrogate_value(a, _w))
            path, _at, _sc, sub = _greedy_core(
                search, score_fn, patience, log, f"dink{it}")
        for row in sub:
            row = dict(row)
            row["note"] = f"r{it}:{row.get('note') or ''}"
            curve.append(row)
        sel, f1 = _best_prefix(search, path, log, f"dink{it}")
        hist.append({"round": it, "theta": round(counts_to_f1(agg), 4),
                     "weights": [round(x, 6) for x in w],
                     "k": len(sel), "true_f1": round(f1, 4)})
        if f1 <= best_f1 + EPS:
            log(f"  [dinkelbach] round {it} did not improve "
                f"({f1:.4f} <= {best_f1:.4f}); converged")
            break
        best_sel, best_f1, best_path = sel, f1, path
        agg = search.pooled_counts(search.evaluate(set(sel)))
    else:
        log(f"  [dinkelbach] hit dink_rounds={rounds}")

    log(f"  [dinkelbach] best true F1={best_f1:.4f} at |S|={len(best_sel)}")
    return Result(best_sel, curve, _prefix_ladder(best_path),
                  {"rounds": hist, "inner": inner, "train_score": best_f1})


# ---------------------------------------------------------------------------
# 7-8. Pareto optimisation: POSS / PORSS  (Qian, Yu & Zhou)
# ---------------------------------------------------------------------------

def _front_add(front, k, f1, active, pp):
    """Insert into the size-indexed non-dominated front; True if it was kept.

    The bi-objective is (maximise F1, minimise |S|), so the front is the set of
    solutions no other solution beats on both.  Keeping one entry per size and
    enforcing "F1 strictly increasing in k" is that same front, with ties at
    equal size resolved in favour of the incumbent."""
    for j, e in front.items():
        if j <= k and e["f1"] >= f1 - EPS:
            return False                       # dominated by an existing entry
    front[k] = {"f1": f1, "active": frozenset(active), "pp": pp}
    for j in [j for j, e in front.items() if j > k and e["f1"] <= f1 + EPS]:
        del front[j]
    return True


def _poss(search, opts, log, recomb):
    tag = "porss" if recomb else "poss"
    iters = opts.get("poss_iters", 5000)
    seed_mode = opts.get("poss_seed", "greedy")
    rng = random.Random(opts.get("seed", 0))
    units = list(search.candidate_units())
    n = len(units)
    if n == 0:
        return Result([], [], None, {"note": "empty pool"})
    p_flip = 1.0 / n

    front = {}
    pp0 = search.evaluate(set())
    _front_add(front, 0, search.pooled_f1(pp0), frozenset(), pp0)

    if seed_mode == "greedy":
        # Warm start from the greedy path's prefixes.  The papers start from
        # the empty set; seeding is a deliberate deviation that makes the
        # "never worse than greedy" property hold from iteration 0 instead of
        # in expectation, and saves the run from re-deriving greedy by mutation.
        path, _at, _sc, _c = _greedy_core(
            search, counts_to_f1, opts.get("patience", 25), log,
            f"{tag}-seed", record=False)
        acc, pp = set(), pp0
        for i, u in enumerate(path, 1):
            acc.add(u)
            pp = search.rescore(pp, acc, (u,))
            _front_add(front, i, search.pooled_f1(pp), frozenset(acc), pp)

    log(f"  [{tag}] n={n} units, seed={seed_mode}, front={len(front)}, "
        f"iters={iters}")
    kept = 0
    for t in range(1, iters + 1):
        keys = list(front)
        pk = rng.choice(keys)
        parent = front[pk]
        child = set(parent["active"])
        if recomb and len(keys) > 1:
            # PORSS: one-point crossover on the fixed unit ordering, then
            # mutate.  Recombination mixes rule blocks that were discovered in
            # different parts of the front, which bit-flips alone reach only
            # by a long chain of accepted single steps.
            ok = rng.choice([j for j in keys if j != pk])
            other = front[ok]["active"]
            cut = rng.randrange(n + 1)
            child = ({u for u in units[:cut] if u in parent["active"]}
                     | {u for u in units[cut:] if u in other})
        for u in units:
            if rng.random() < p_flip:
                child.discard(u) if u in child else child.add(u)
        changed = child ^ set(parent["active"])
        if not changed:
            continue
        pp = search.rescore(parent["pp"], child, changed)
        f1 = search.pooled_f1(pp)
        if _front_add(front, len(child), f1, child, pp):
            kept += 1
        if t % max(1, iters // 10) == 0:
            bk = max(front, key=lambda j: front[j]["f1"])
            log(f"  [{tag}] iter {t}/{iters}: front={len(front)} "
                f"kept={kept} best F1={front[bk]['f1']:.4f} at k={bk}")

    best_k = max(front, key=lambda j: (front[j]["f1"], -j))
    best = front[best_k]
    ladder = [(j, front[j]["active"]) for j in sorted(front)]
    curve = [search.row(j, None, front[j]["pp"], note=f"front k={j}")
             for j in sorted(front)]
    log(f"  [{tag}] done: front={len(front)} rungs, best F1="
        f"{best['f1']:.4f} at k={best_k}")
    return Result(sorted(best["active"]), curve, ladder,
                  {"iterations": iters, "accepted": kept,
                   "front_size": len(front), "seed_mode": seed_mode,
                   "recombination": recomb, "train_score": best["f1"]})


def poss(search, opts, log=print):
    """Pareto Optimization for Subset Selection (Qian, Yu & Zhou, NeurIPS 2015).

    Recasts "pick the best subset" as the bi-objective problem (maximise F1,
    minimise |S|) and keeps an archive of non-dominated solutions, mutated by
    per-bit flips at rate 1/n.  It is provably never worse than greedy, is not
    trapped by greedy's single-path trajectory, and degrades gracefully when
    the objective is not submodular (the analysis goes through the
    submodularity ratio, not submodularity itself).

    Practical bonus for this pipeline: one run returns the ENTIRE
    size-vs-F1 frontier, so the CV stopping-size choice gets a real curve to
    score on held-out folds instead of a single greedy trajectory."""
    return _poss(search, opts, log, recomb=False)


def porss(search, opts, log=print):
    """POSS with recombination (Qian et al., 2022) -- crossover then mutate."""
    return _poss(search, opts, log, recomb=True)


# ---------------------------------------------------------------------------
# registry (ordered classical -> contemporary; this order drives --help)
# ---------------------------------------------------------------------------

ALGOS = OrderedDict([
    ("greedy", greedy),
    ("lazy", lazy),
    ("localsearch", localsearch),
    ("distorted", distorted),
    ("dinkelbach", dinkelbach),
    ("poss", poss),
    ("porss", porss),
])

BLURBS = OrderedDict([
    ("greedy", "forward selection on pooled F1 (baseline)"),
    ("lazy", "CELF lazy forward selection (same intent, far fewer evals)"),
    ("localsearch", "add/drop/swap to a local optimum (escapes fwd+bwd)"),
    ("distorted", "distorted greedy for submodular-minus-modular (ICML 2019)"),
    ("dinkelbach", "fractional programming on the F1 ratio (re-linearised)"),
    ("poss", "Pareto optimisation over (F1, -|S|) (NeurIPS 2015)"),
    ("porss", "POSS + recombination (2022)"),
])


def run(name, search, opts, log=print):
    if name not in ALGOS:
        raise SystemExit(f"unknown --search-algo {name!r}; "
                         f"choose from {', '.join(ALGOS)}")
    return ALGOS[name](search, opts, log)
