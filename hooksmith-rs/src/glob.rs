//! File pattern matching for the `files = "..."` hook key. Backed by the
//! `globset` crate so the patterns compile once per hook and match in O(n).

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
