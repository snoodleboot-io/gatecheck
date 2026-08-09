//! Rayon-backed dynamic DAG execution engine (STY-0014, dynamic scheduler STY-0029).
//!
//! Consumes the full dependency graph produced by the Python planner
//! (`hooksmith.runner.build_plan`) and executes each hook by calling back into a
//! Python callable. Unlike the original wave scheduler — which barriered at each
//! topological level, so the slowest hook in a level blocked the next — this
//! scheduler is *dynamic*: a hook starts the moment all its dependencies finish,
//! while unrelated peers are still running. On uneven graphs this cuts wall-clock.
//!
//! The GIL is released around the rayon pool (`allow_threads`) and re-acquired per
//! callback (`Python::with_gil`), so a hook's subprocess wait overlaps with its
//! peers'. Orchestration (in-degree bookkeeping, spawning) happens on a single
//! thread draining a completion channel — the worker tasks only run one callback
//! and report back, so no hook state is shared mutably across threads.

use std::collections::VecDeque;
use std::sync::mpsc;

use pyo3::prelude::*;

/// Execute the dependency graph `(nodes, deps)`, calling `execute(id) -> int` per node.
///
/// `nodes` is a topologically-valid ordering of hook ids; `deps[i]` lists the
/// indices (into `nodes`) of node `i`'s dependencies. `execute` returns a status
/// code (0 = passed, non-zero = failed/error). A node is scheduled once every one
/// of its dependencies has completed. When `fail_fast` is true, the first non-zero
/// status stops the scheduling of any not-yet-started node (in-flight nodes still
/// finish), so a hook downstream of a failure never starts.
///
/// `max_workers` caps the number of hooks in flight at once (a group's
/// `max-workers`; `1` = serial). `None` runs unbounded on rayon's global pool.
///
/// Returns the ids that were executed, in `nodes` (input) order — deterministic
/// regardless of completion timing.
#[pyfunction]
#[pyo3(signature = (nodes, deps, execute, fail_fast, max_workers=None))]
fn run_graph(
    py: Python<'_>,
    nodes: Vec<String>,
    deps: Vec<Vec<usize>>,
    execute: PyObject,
    fail_fast: bool,
    max_workers: Option<usize>,
) -> PyResult<Vec<String>> {
    let n = nodes.len();
    let cap = max_workers.filter(|&w| w > 0).unwrap_or(usize::MAX);

    // in-degree per node + reverse edges (who becomes eligible when i finishes).
    let mut indegree: Vec<usize> = vec![0; n];
    let mut dependents: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (i, node_deps) in deps.iter().enumerate() {
        indegree[i] = node_deps.len();
        for &d in node_deps {
            dependents[d].push(i);
        }
    }

    // Release the GIL so rayon workers can each re-acquire it per callback. The scope
    // closure owns the completion channel and the mutable bookkeeping, and returns the
    // executed-flags and the first callback error (if any) back out. `execute` and
    // `nodes` are borrowed for the whole call, so they outlive the rayon scope.
    let execute_ref = &execute;
    let nodes_ref = &nodes;
    let (executed, first_error): (Vec<bool>, Option<PyErr>) = py.allow_threads(|| {
        let (tx, rx) = mpsc::channel::<(usize, PyResult<i64>)>();

        rayon::scope(move |scope| {
            let mut executed = vec![false; n];
            let mut first_error: Option<PyErr> = None;
            let mut indegree = indegree;
            let mut ready: VecDeque<usize> = VecDeque::new();
            let mut outstanding = 0usize;
            let mut aborted = false;

            // Spawn one node's callback onto the pool, reporting (index, result). Inlined
            // (not a helper closure) so the task closure inherits the real `'scope`.
            macro_rules! spawn {
                ($i:expr) => {{
                    let i = $i;
                    let id = nodes_ref[i].clone();
                    let tx = tx.clone();
                    scope.spawn(move |_| {
                        let outcome = Python::with_gil(|py| {
                            execute_ref.call1(py, (id.as_str(),))?.extract::<i64>(py)
                        });
                        let _ = tx.send((i, outcome));
                    });
                }};
            }

            // Launch ready nodes up to the concurrency cap (skipped once aborted).
            macro_rules! pump {
                () => {{
                    while !aborted && outstanding < cap {
                        match ready.pop_front() {
                            Some(i) => {
                                executed[i] = true;
                                outstanding += 1;
                                spawn!(i);
                            }
                            None => break,
                        }
                    }
                }};
            }

            // Seed the roots (no dependencies), in input order, then fill up to the cap.
            for (i, &degree) in indegree.iter().enumerate() {
                if degree == 0 {
                    ready.push_back(i);
                }
            }
            pump!();

            while outstanding > 0 {
                let (i, outcome) = rx.recv().expect("worker dropped the channel");
                outstanding -= 1;

                match outcome {
                    Ok(status) => {
                        if fail_fast && status != 0 {
                            aborted = true;
                        }
                    }
                    Err(err) => {
                        if first_error.is_none() {
                            first_error = Some(err);
                        }
                        aborted = true; // a callback error always stops new scheduling
                    }
                }

                // Free dependents; enqueue any that are now ready.
                for &dep in &dependents[i] {
                    indegree[dep] -= 1;
                    if indegree[dep] == 0 && !executed[dep] {
                        ready.push_back(dep);
                    }
                }
                pump!();
            }

            (executed, first_error)
        })
    });

    if let Some(err) = first_error {
        return Err(err);
    }

    Ok(nodes
        .into_iter()
        .zip(executed)
        .filter_map(|(id, ran)| if ran { Some(id) } else { None })
        .collect())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_graph, m)?)?;
    Ok(())
}
