//! Rayon-backed parallel execution engine (STY-0014).
//!
//! Consumes the parallelizable waves produced by the Python planner
//! (`gatecheck.runner.build_plan`) and executes each hook by calling back into a
//! Python callable. Hooks within a wave run concurrently on the rayon pool; the
//! GIL is released around the pool (`allow_threads`) and re-acquired per callback
//! (`Python::with_gil`), so a hook's subprocess wait overlaps with its peers'.

use pyo3::prelude::*;
use rayon::prelude::*;

/// Execute `waves` of hook ids, calling `execute(id) -> int` for each.
///
/// Each wave's ids run in parallel; `execute` returns a status code (0 = passed,
/// non-zero = failed/error). When `fail_fast` is true, no further wave is started
/// after a wave in which any hook returns a non-zero status (the current wave still
/// finishes). Returns the ids that were executed, in wave-then-input order.
#[pyfunction]
fn run_waves(
    py: Python<'_>,
    waves: Vec<Vec<String>>,
    execute: PyObject,
    fail_fast: bool,
) -> PyResult<Vec<String>> {
    let mut executed: Vec<String> = Vec::new();
    for wave in waves {
        // Release the GIL so rayon workers can each re-acquire it per callback.
        let statuses: Vec<i64> = py.allow_threads(|| {
            wave.par_iter()
                .map(|id| {
                    Python::with_gil(|py| execute.call1(py, (id.as_str(),))?.extract::<i64>(py))
                })
                .collect::<PyResult<Vec<i64>>>()
        })?;

        executed.extend(wave.iter().cloned());
        if fail_fast && statuses.iter().any(|&status| status != 0) {
            break;
        }
    }
    Ok(executed)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_waves, m)?)?;
    Ok(())
}
