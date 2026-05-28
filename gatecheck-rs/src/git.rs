//! Minimal git plumbing — staged files, branch name, changed files between refs.
//! Shells out to `git`; no libgit2 dependency.

use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
