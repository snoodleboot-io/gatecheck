//! Reserved for native dependency-graph helpers. The topological ordering and the
//! dynamic (non-wave-barrier) scheduling currently live in the Python planner
//! (`build_plan`) and `runner::run_graph` respectively.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Public functions land here as the implementation is filled in.
    Ok(())
}
