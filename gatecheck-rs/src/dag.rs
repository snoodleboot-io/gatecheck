//! Kahn's-algorithm topological sort over hook dependencies, grouped into waves
//! that can be executed in parallel.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Public functions land here as the implementation is filled in.
    Ok(())
}
