//! Cache-key generation (SHA-256 over the inputs that should invalidate a hook)
//! and the structured trace that backs `gatecheck cache why`.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
