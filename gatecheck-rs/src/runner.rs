//! Rayon-backed parallel subprocess runner. Consumes the waves produced by
//! `dag` and executes each hook's command, returning per-hook results.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
