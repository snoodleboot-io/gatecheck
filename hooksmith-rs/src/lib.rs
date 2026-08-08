//! hooksmith_core — native runtime for hooksmith.
//!
//! See planning/adr/0001-python-host-rust-core.md for the split rationale.

use pyo3::prelude::*;

mod cache;
mod dag;
mod git;
mod glob;
mod runner;

/// Python module entry point. Re-exports every submodule's public surface.
#[pymodule]
fn hooksmith_core(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    let _ = py;
    cache::register(m)?;
    dag::register(m)?;
    git::register(m)?;
    glob::register(m)?;
    runner::register(m)?;
    Ok(())
}
